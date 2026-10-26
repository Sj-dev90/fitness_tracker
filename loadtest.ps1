param(
    [int]$Requests    = 2000,
    [int]$Concurrency = 50
)

# Never let PowerShell silently eat errors from OUR logic
$ErrorActionPreference = "Stop"
$env:DOCKER_CLI_HINTS  = "false"

# ──────────────────────────────────────────────────────────────────────────────
# Invoke-Docker: Run a docker command via System.Diagnostics.Process so that
# Docker's own stderr (progress lines, "Pulling", "Completed N requests", etc.)
# never hits the PowerShell pipeline and causes NativeCommandError truncation.
# Returns a [PSCustomObject] with .Stdout, .Stderr, and .ExitCode.
# ──────────────────────────────────────────────────────────────────────────────
function Invoke-Docker {
    param([string]$Arguments)

    $psi                        = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName               = "docker"
    $psi.Arguments              = $Arguments
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError  = $true
    $psi.UseShellExecute        = $false
    $psi.CreateNoWindow         = $true

    $proc = [System.Diagnostics.Process]::Start($psi)
    # Read both streams fully before WaitForExit to avoid deadlock
    $stdout = $proc.StandardOutput.ReadToEnd()
    $stderr = $proc.StandardError.ReadToEnd()
    $proc.WaitForExit()

    return [PSCustomObject]@{
        Stdout   = $stdout
        Stderr   = $stderr
        ExitCode = $proc.ExitCode
        # ab writes its summary to stdout; progress ("Completed N requests") to stderr
        Combined = $stdout + "`n" + $stderr
    }
}

# ──────────────────────────────────────────────────────────────────────────────
# WaitFor-Service: Poll until nginx+backend are serving /api/loadtest
# ──────────────────────────────────────────────────────────────────────────────
function WaitFor-Service {
    param([int]$MaxAttempts = 40)
    Write-Host "Waiting for service to be healthy..." -NoNewline
    for ($i = 0; $i -lt $MaxAttempts; $i++) {
        try {
            $resp = Invoke-WebRequest -Uri "http://localhost/api/loadtest" `
                        -UseBasicParsing -TimeoutSec 4 -ErrorAction SilentlyContinue
            if ($resp -and $resp.StatusCode -eq 200) {
                # Quick smoke-test from inside Docker (proves host.docker.internal resolves)
                $result = Invoke-Docker "run --rm httpd:alpine ab -s 30 -n 1 -c 1 http://host.docker.internal/api/loadtest"
                $combined = $result.Stdout + "`n" + $result.Stderr
                if ($combined -match 'Complete requests:\s+1') {
                    Write-Host " Ready!" -ForegroundColor Green
                    return $true
                }
            }
        } catch { }
        Start-Sleep -Seconds 2
        Write-Host "." -NoNewline
    }
    Write-Host " Timed out!" -ForegroundColor Red
    return $false
}

# ──────────────────────────────────────────────────────────────────────────────
# Run-Benchmark: Run ab via Invoke-Docker, parse strictly, throw on any failure
# ──────────────────────────────────────────────────────────────────────────────
function Run-Benchmark {
    param(
        [int]$n,
        [int]$c,
        [string]$RawFile
    )

    $abArgs = "run --rm httpd:alpine ab -s 120 -n $n -c $c http://host.docker.internal/api/loadtest"
    Write-Host "  Running: docker $abArgs" -ForegroundColor DarkGray

    $result = Invoke-Docker $abArgs

    # ab prints its report to stdout; progress lines go to stderr.
    # Save stdout (the actual report) as the canonical raw file.
    $rawReport = $result.Stdout
    if ([string]::IsNullOrWhiteSpace($rawReport)) {
        # Fall back to combined in case something unusual happened
        $rawReport = $result.Combined
    }

    $rawReport | Out-File -FilePath $RawFile -Encoding utf8
    Write-Host "  Raw ab output saved to $RawFile" -ForegroundColor Cyan

    # ── Parse Requests per second ─────────────────────────────────────────────
    if (-not ($rawReport -match 'Requests per second:\s+([\d.]+)')) {
        Write-Host "`n[ERROR] Could not parse 'Requests per second'. Raw ab output:" -ForegroundColor Red
        Write-Host "--- STDOUT ---"
        Write-Host $result.Stdout
        Write-Host "--- STDERR ---"
        Write-Host $result.Stderr
        throw "Benchmark failed: could not parse 'Requests per second'."
    }
    $rps = [double]$matches[1]

    # ── Parse Time per request (mean) — FIRST occurrence only ─────────────────
    if (-not ($rawReport -match 'Time per request:\s+([\d.]+)\s+\[ms\]\s+\(mean\)')) {
        Write-Host "`n[ERROR] Could not parse 'Time per request (mean)'. Raw ab output:" -ForegroundColor Red
        Write-Host "--- STDOUT ---"
        Write-Host $result.Stdout
        Write-Host "--- STDERR ---"
        Write-Host $result.Stderr
        throw "Benchmark failed: could not parse 'Time per request (mean)'."
    }
    $meanTime = [double]$matches[1]

    # ── Parse Failed requests ─────────────────────────────────────────────────
    if (-not ($rawReport -match 'Failed requests:\s+(\d+)')) {
        Write-Host "`n[ERROR] Could not parse 'Failed requests'. Raw ab output:" -ForegroundColor Red
        Write-Host "--- STDOUT ---"
        Write-Host $result.Stdout
        Write-Host "--- STDERR ---"
        Write-Host $result.Stderr
        throw "Benchmark failed: could not parse 'Failed requests'."
    }
    $failed = [int]$matches[1]

    # ── Parse Time taken for tests ────────────────────────────────────────────
    if (-not ($rawReport -match 'Time taken for tests:\s+([\d.]+)')) {
        Write-Host "`n[ERROR] Could not parse 'Time taken for tests'. Raw ab output:" -ForegroundColor Red
        Write-Host "--- STDOUT ---"
        Write-Host $result.Stdout
        Write-Host "--- STDERR ---"
        Write-Host $result.Stderr
        throw "Benchmark failed: could not parse 'Time taken for tests'."
    }
    $timeTaken = [double]$matches[1]

    return [PSCustomObject]@{
        RPS      = $rps
        MeanTime = $meanTime
        Failed   = $failed
        TimeTaken= $timeTaken
    }
}

# ══════════════════════════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════════════════════════
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

try {
    Write-Host "==========================================================" -ForegroundColor Cyan
    Write-Host " Fitness Tracker Load Test: 1 Instance vs 3 Instances"    -ForegroundColor Cyan
    Write-Host " Endpoint  : /api/loadtest  (real MongoDB Atlas read)"     -ForegroundColor Cyan
    Write-Host " Requests  : $Requests    Concurrency: $Concurrency"       -ForegroundColor Cyan
    Write-Host "==========================================================" -ForegroundColor Cyan

    # ── Step 1: Tear down anything already running ────────────────────────────
    Write-Host "`n[1/5] Tearing down any existing containers..." -ForegroundColor Yellow
    $ErrorActionPreference = "Continue"   # compose down is OK to "fail" if nothing running
    docker compose -f "$scriptDir\docker-compose.single.yml" down --remove-orphans 2>&1 | Out-Null
    docker compose -f "$scriptDir\docker-compose.yml"        down --remove-orphans 2>&1 | Out-Null
    $ErrorActionPreference = "Stop"

    # ── Step 2: Build image ───────────────────────────────────────────────────
    Write-Host "`n[2/5] Building Docker image..." -ForegroundColor Yellow
    $ErrorActionPreference = "Continue"
    docker compose -f "$scriptDir\docker-compose.yml" build 2>&1 | Out-Null
    $ErrorActionPreference = "Stop"

    # ── Step 3: 1-instance benchmark ──────────────────────────────────────────
    Write-Host "`n[3/5] Starting 1-instance setup (nginx-single)..." -ForegroundColor Yellow
    $ErrorActionPreference = "Continue"
    docker compose -f "$scriptDir\docker-compose.single.yml" up -d 2>&1 | Out-Null
    $ErrorActionPreference = "Stop"

    if (-not (WaitFor-Service)) {
        throw "Single-instance setup failed to become ready."
    }

    Write-Host "Benchmarking 1 instance..." -ForegroundColor Green
    $result1 = Run-Benchmark -n $Requests -c $Concurrency -RawFile "$scriptDir\ab_raw_1instance.txt"
    Write-Host "  => $($result1.RPS) req/s  |  $($result1.MeanTime) ms/req  |  $($result1.Failed) failed" -ForegroundColor Green

    # ── Step 4: 3-instance benchmark ──────────────────────────────────────────
    Write-Host "`n[4/5] Switching to 3-instance setup (Nginx load-balanced)..." -ForegroundColor Yellow
    $ErrorActionPreference = "Continue"
    docker compose -f "$scriptDir\docker-compose.single.yml" down --remove-orphans 2>&1 | Out-Null
    docker compose -f "$scriptDir\docker-compose.yml" up -d 2>&1 | Out-Null
    $ErrorActionPreference = "Stop"

    if (-not (WaitFor-Service)) {
        throw "3-instance setup failed to become ready."
    }

    Write-Host "Pausing 5 s for Atlas connection-pool warm-up..." -ForegroundColor Gray
    Start-Sleep -Seconds 5

    Write-Host "Benchmarking 3 instances..." -ForegroundColor Green
    $result3 = Run-Benchmark -n $Requests -c $Concurrency -RawFile "$scriptDir\ab_raw_3instances.txt"
    Write-Host "  => $($result3.RPS) req/s  |  $($result3.MeanTime) ms/req  |  $($result3.Failed) failed" -ForegroundColor Green

    # ── Step 5: Print comparison table ────────────────────────────────────────
    Write-Host "`n[5/5] Compiling results..." -ForegroundColor Yellow

    $rpsDiff  = $result3.RPS - $result1.RPS
    $rpsPct   = if ($result1.RPS -gt 0) { [math]::Round(($rpsDiff / $result1.RPS) * 100, 2) } else { 0 }
    $timeDiff = [math]::Round($result1.MeanTime - $result3.MeanTime, 2)
    $sign     = if ($rpsPct -ge 0) { "+$rpsPct%" } else { "$rpsPct%" }
    $tSign    = if ($timeDiff -ge 0) { "-${timeDiff} ms faster" } else { "+$([math]::Abs($timeDiff)) ms slower" }

    $table = @"
================================================================================
LOAD TEST COMPARISON: 1 INSTANCE vs 3 INSTANCES BEHIND NGINX
Endpoint    : /api/loadtest  (Real MongoDB Atlas read, 20 documents)
Requests    : $Requests
Concurrency : $Concurrency
Date/Time   : $(Get-Date -Format "yyyy-MM-dd HH:mm:ss")
================================================================================
Metric                           1 Instance              3 Instances             Change
--------------------------------------------------------------------------------
Requests per second (RPS)        $($result1.RPS.ToString("F2").PadRight(23)) $($result3.RPS.ToString("F2").PadRight(23)) $sign
Time per request (mean) [ms]     $($result1.MeanTime.ToString("F2").PadRight(23)) $($result3.MeanTime.ToString("F2").PadRight(23)) $tSign
Failed requests                  $($result1.Failed.ToString().PadRight(23)) $($result3.Failed.ToString().PadRight(23)) delta=$($result3.Failed - $result1.Failed)
Total time taken [s]             $($result1.TimeTaken.ToString("F2").PadRight(23)) $($result3.TimeTaken.ToString("F2").PadRight(23))
================================================================================
"@

    Write-Host $table
    $table | Out-File -FilePath "$scriptDir\loadtest_results.txt" -Encoding utf8
    Write-Host "Results saved to $scriptDir\loadtest_results.txt" -ForegroundColor Green

} finally {
    Write-Host "`n[Cleanup] Tearing down all test containers..." -ForegroundColor Yellow
    $ErrorActionPreference = "Continue"
    docker compose -f "$scriptDir\docker-compose.single.yml" down --remove-orphans 2>&1 | Out-Null
    docker compose -f "$scriptDir\docker-compose.yml"        down --remove-orphans 2>&1 | Out-Null
    Write-Host "Teardown complete." -ForegroundColor Green
}
