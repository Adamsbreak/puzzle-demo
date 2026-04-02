$cases = @(
  @{ File = "tc01_multiple_legal_stops.json"; ExpectedStatus = "solved"; ExpectedStepCount = 1 },
  @{ File = "tc02_fixed_adjacent_blocks.json"; ExpectedStatus = "no-solution"; ExpectedStepCount = $null },
  @{ File = "tc03_stop_mid_opens_path.json"; ExpectedStatus = "solved"; ExpectedStepCount = 2 },
  @{ File = "tc04_large_piece_footprint.json"; ExpectedStatus = "no-solution"; ExpectedStepCount = $null },
  @{ File = "tc05_horizontal_forbids_vertical.json"; ExpectedStatus = "no-solution"; ExpectedStepCount = $null },
  @{ File = "tc06_edge_goal_full.json"; ExpectedStatus = "no-solution"; ExpectedStepCount = $null },
  @{ File = "tc06_edge_goal_partial.json"; ExpectedStatus = "solved"; ExpectedStepCount = 1 },
  @{ File = "tc07_block_cannot_enter_edge_goal.json"; ExpectedStatus = "no-solution"; ExpectedStepCount = $null },
  @{ File = "tc08_shortest_operation_count.json"; ExpectedStatus = "solved"; ExpectedStepCount = 1 },
  @{ File = "tc03_target_lane_priority.json"; ExpectedStatus = "solved"; ExpectedStepCount = 1 },
  @{ File = "tc07_edge_goal_last_step_only.json"; ExpectedStatus = "no-solution"; ExpectedStepCount = $null }
)

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Push-Location (Join-Path $root "..")

foreach ($case in $cases) {
  $path = Join-Path $root $case.File
  Write-Host ""
  Write-Host "==> $($case.File)" -ForegroundColor Cyan
  $raw = Get-Content $path -Raw
  $json = $raw | mvn -q exec:java
  $result = $json | ConvertFrom-Json

  $statusPass = $result.status -eq $case.ExpectedStatus
  $stepPass = $true
  if ($null -ne $case.ExpectedStepCount) {
    $stepPass = [int]$result.stepCount -eq [int]$case.ExpectedStepCount
  }

  if ($statusPass -and $stepPass) {
    Write-Host "PASS  status=$($result.status) stepCount=$($result.stepCount)" -ForegroundColor Green
  } else {
    Write-Host "FAIL  status=$($result.status) stepCount=$($result.stepCount)" -ForegroundColor Red
    Write-Host "      expected status=$($case.ExpectedStatus) stepCount=$($case.ExpectedStepCount)"
  }
}

Pop-Location
