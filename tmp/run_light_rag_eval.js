const fs = require("fs");
const path = require("path");

const ROOT = path.resolve(__dirname, "..");
const CORPUS_PATH = path.join(ROOT, "docs", "light_rag_corpus.json");
const DATASET_PATH = path.join(ROOT, "docs", "light_rag_eval_dataset.json");
const RESULT_JSON_PATH = path.join(ROOT, "tmp", "light_rag_eval_results.json");
const RESULT_MD_PATH = path.join(ROOT, "tmp", "light_rag_eval_results.md");

function loadJson(filePath) {
  return JSON.parse(fs.readFileSync(filePath, "utf8"));
}

function tokenize(text) {
  const lowered = String(text || "").toLowerCase();
  const wordTokens = lowered.match(/[a-z0-9\-_]+/g) || [];
  const chineseChars = [...lowered].filter((ch) => ch >= "\u4e00" && ch <= "\u9fff");
  return [...wordTokens, ...chineseChars];
}

function normalizeText(text) {
  return String(text || "").trim().toLowerCase().replace(/\s+/g, " ");
}

function scoreEntry(query, entry) {
  const queryNorm = normalizeText(query);
  const queryTokens = new Set(tokenize(query));
  const haystack = [
    entry.title || "",
    entry.summary || "",
    (entry.keywords || []).join(" "),
    entry.id || "",
  ].join(" ");
  const haystackTokens = new Set(tokenize(haystack));

  let overlap = 0;
  for (const token of queryTokens) {
    if (haystackTokens.has(token)) overlap += 1;
  }
  let score = overlap;

  for (const keyword of entry.keywords || []) {
    const keywordNorm = normalizeText(keyword);
    if (keywordNorm && queryNorm.includes(keywordNorm)) {
      score += 3.0;
    } else {
      const keywordTokens = new Set(tokenize(keyword));
      let localOverlap = 0;
      for (const token of queryTokens) {
        if (keywordTokens.has(token)) localOverlap += 1;
      }
      score += 0.25 * localOverlap;
    }
  }

  const titleNorm = normalizeText(entry.title || "");
  if (titleNorm && queryNorm.includes(titleNorm)) {
    score += 4.0;
  }

  const entryId = normalizeText(entry.id || "");
  const tail = entryId.split(".").pop();
  if (tail && queryNorm.includes(tail)) {
    score += 2.0;
  }

  if (entry.type === "rule_doc") {
    if (["why", "difference", "rule", "rules", "interface", "architecture", "bridge"].some((token) => queryNorm.includes(token))) {
      score += 0.2;
    }
  } else if (entry.type === "case") {
    if (["case", "example", "regression", "tc"].some((token) => queryNorm.includes(token))) {
      score += 0.2;
    }
  }

  return score;
}

function rankEntries(query, corpusEntries) {
  return corpusEntries
    .map((entry) => ({
      id: entry.id,
      type: entry.type,
      title: entry.title,
      score: Number(scoreEntry(query, entry).toFixed(4)),
    }))
    .sort((a, b) => (b.score - a.score) || a.id.localeCompare(b.id));
}

function reciprocalRank(rankedIds, expectedIds) {
  for (let index = 0; index < rankedIds.length; index += 1) {
    if (expectedIds.has(rankedIds[index])) {
      return 1 / (index + 1);
    }
  }
  return 0;
}

function precisionAtK(rankedIds, expectedIds, k) {
  if (k <= 0) return 0;
  const topIds = rankedIds.slice(0, k);
  if (topIds.length === 0) return 0;
  const hits = topIds.filter((entryId) => expectedIds.has(entryId)).length;
  return hits / topIds.length;
}

function recallAtK(rankedIds, expectedIds, k) {
  if (expectedIds.size === 0) return 1;
  const hits = rankedIds.slice(0, k).filter((entryId) => expectedIds.has(entryId)).length;
  return hits / expectedIds.size;
}

function summarize(metricLists) {
  const summary = {};
  for (const [name, values] of Object.entries(metricLists).sort(([a], [b]) => a.localeCompare(b))) {
    summary[name] = values.length ? Number((values.reduce((sum, value) => sum + value, 0) / values.length).toFixed(4)) : 0;
  }
  return summary;
}

function evaluate(corpus, dataset, kValues = [1, 3, 5]) {
  const entries = corpus.entries;
  const samples = dataset.samples;
  const overallMetrics = {};
  const categoryMetrics = {};
  const perSampleResults = [];

  function pushMetric(bucket, name, value) {
    if (!bucket[name]) bucket[name] = [];
    bucket[name].push(value);
  }

  for (const sample of samples) {
    const expectedIds = new Set([...(sample.expected_rule_ids || []), ...(sample.expected_case_ids || [])]);
    const ranked = rankEntries(sample.query, entries);
    const rankedIds = ranked.map((item) => item.id);
    const metrics = {};

    const rr = reciprocalRank(rankedIds, expectedIds);
    pushMetric(overallMetrics, "mrr", rr);
    if (!categoryMetrics[sample.category]) categoryMetrics[sample.category] = {};
    pushMetric(categoryMetrics[sample.category], "mrr", rr);
    metrics.mrr = Number(rr.toFixed(4));

    for (const k of kValues) {
      const hit = rankedIds.slice(0, k).some((entryId) => expectedIds.has(entryId)) ? 1 : 0;
      const precision = precisionAtK(rankedIds, expectedIds, k);
      const recall = recallAtK(rankedIds, expectedIds, k);

      pushMetric(overallMetrics, `hit_rate@${k}`, hit);
      pushMetric(overallMetrics, `precision@${k}`, precision);
      pushMetric(overallMetrics, `recall@${k}`, recall);

      pushMetric(categoryMetrics[sample.category], `hit_rate@${k}`, hit);
      pushMetric(categoryMetrics[sample.category], `precision@${k}`, precision);
      pushMetric(categoryMetrics[sample.category], `recall@${k}`, recall);

      metrics[`hit_rate@${k}`] = Number(hit.toFixed(4));
      metrics[`precision@${k}`] = Number(precision.toFixed(4));
      metrics[`recall@${k}`] = Number(recall.toFixed(4));
    }

    perSampleResults.push({
      id: sample.id,
      category: sample.category,
      query: sample.query,
      expected_ids: [...expectedIds].sort(),
      top_hits: ranked.slice(0, 5),
      metrics,
    });
  }

  const byCategory = {};
  for (const [category, metrics] of Object.entries(categoryMetrics).sort(([a], [b]) => a.localeCompare(b))) {
    byCategory[category] = summarize(metrics);
  }

  return {
    generated_at_utc: new Date().toISOString(),
    corpus_size: entries.length,
    sample_count: samples.length,
    k_values: kValues,
    overall: summarize(overallMetrics),
    by_category: byCategory,
    samples: perSampleResults,
  };
}

function renderMarkdown(result) {
  const lines = [];
  lines.push("# Lightweight RAG Eval Results", "");
  lines.push(`- Generated at (UTC): \`${result.generated_at_utc}\``);
  lines.push(`- Corpus size: \`${result.corpus_size}\``);
  lines.push(`- Sample count: \`${result.sample_count}\``, "");
  lines.push("## Overall", "");
  for (const [metric, value] of Object.entries(result.overall)) {
    lines.push(`- \`${metric}\`: \`${value}\``);
  }
  lines.push("", "## By Category", "");
  for (const [category, metrics] of Object.entries(result.by_category)) {
    lines.push(`### ${category}`);
    for (const [metric, value] of Object.entries(metrics)) {
      lines.push(`- \`${metric}\`: \`${value}\``);
    }
    lines.push("");
  }
  lines.push("## Sample Highlights", "");
  for (const sample of result.samples.slice(0, 8)) {
    lines.push(`### ${sample.id} - ${sample.category}`);
    lines.push(`- Query: ${sample.query}`);
    lines.push(`- Expected: ${sample.expected_ids.join(", ")}`);
    lines.push(`- Top 3: ${sample.top_hits.slice(0, 3).map((item) => `${item.id} (${item.score})`).join(", ")}`);
    lines.push(`- MRR: \`${sample.metrics.mrr}\``, "");
  }
  return lines.join("\n");
}

function main() {
  const corpus = loadJson(CORPUS_PATH);
  const dataset = loadJson(DATASET_PATH);
  const result = evaluate(corpus, dataset);

  fs.writeFileSync(RESULT_JSON_PATH, JSON.stringify(result, null, 2), "utf8");
  fs.writeFileSync(RESULT_MD_PATH, renderMarkdown(result), "utf8");

  console.log("Lightweight RAG evaluation finished.");
  console.log(`Corpus size: ${result.corpus_size}`);
  console.log(`Sample count: ${result.sample_count}`);
  for (const [metric, value] of Object.entries(result.overall)) {
    console.log(`${metric}: ${value}`);
  }
  console.log(`Saved JSON: ${RESULT_JSON_PATH}`);
  console.log(`Saved Markdown: ${RESULT_MD_PATH}`);
}

main();
