param(
    [int]$Requests    = 1000,
    [int]$Concurrency = 20
)

# Strict error handling in script logic
$ErrorActionPreference = "Stop"
$env:DOCKER_CLI_HINTS  = "false"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

# ──────────────────────────────────────────────────────────────────────────────
# Invoke-Docker-Sync: Run a docker command synchronously via System.Diagnostics.Process
# ──────────────────────────────────────────────────────────────────────────────
function Invoke-Docker-Sync {
    param([string]$Arguments)

    $psi                        = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName               = "docker"
    $psi.Arguments              = $Arguments
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError  = $true
    $psi.UseShellExecute        = $false
    $psi.CreateNoWindow         = $true

    $proc = [System.Diagnostics.Process]::Start($psi)
    $stdout = $proc.StandardOutput.ReadToEnd()
    $stderr = $proc.StandardError.ReadToEnd()
    $proc.WaitForExit()

    return [PSCustomObject]@{
        Stdout   = $stdout
        Stderr   = $stderr
        ExitCode = $proc.ExitCode
        Combined = $stdout + "`n" + $stderr
    }
}

# ──────────────────────────────────────────────────────────────────────────────
# WaitFor-Service: Poll until /api/loadtest is answering 200 OK
# ──────────────────────────────────────────────────────────────────────────────
function WaitFor-Service {
    param([int]$MaxAttempts = 40)
    Write-Host "  Waiting for service to be healthy..." -NoNewline
    for ($i = 0; $i -lt $MaxAttempts; $i++) {
        try {
            $resp = Invoke-WebRequest -Uri "http://localhost/api/loadtest" `
                        -UseBasicParsing -TimeoutSec 4 -ErrorAction SilentlyContinue
            if ($resp -and $resp.StatusCode -eq 200) {
                $res = Invoke-Docker-Sync "run --rm httpd:alpine ab -s 10 -n 1 -c 1 http://host.docker.internal/api/loadtest"
                if ($res.Combined -match 'Complete requests:\s+1') {
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
# Run-FailoverBenchmark: Runs ab with -s 10, stops backend2 after 5s,
# safely collects and parses metrics for both normal completion and timeout aborts.
# ──────────────────────────────────────────────────────────────────────────────
function Run-FailoverBenchmark {
    param(
        [string]$ConfigName,
        [int]$n,
        [int]$c,
        [string]$RawFile
    )

    $abArgs = "run --rm httpd:alpine ab -s 10 -n $n -c $c -r http://host.docker.internal/api/loadtest"
    Write-Host "`n  [Test: $ConfigName]" -ForegroundColor Cyan
    Write-Host "  Launching ab in background: docker $abArgs" -ForegroundColor DarkGray

    $sw = [System.Diagnostics.Stopwatch]::StartNew()

    $psi                        = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName               = "docker"
    $psi.Arguments              = $abArgs
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError  = $true
    $psi.UseShellExecute        = $false
    $psi.CreateNoWindow         = $true

    $proc = [System.Diagnostics.Process]::Start($psi)

    Write-Host "  ab running in background. Waiting 5 seconds before stopping backend2..." -ForegroundColor DarkGray
    Start-Sleep -Seconds 5

    Write-Host "  >>> Simulating failure: stopping backend2 now <<<" -ForegroundColor Yellow
    $stopResult = Invoke-Docker-Sync "stop backend2"
    Write-Host "  backend2 stopped. Waiting for ab benchmark to finish..." -ForegroundColor DarkGray

    # Read output streams and wait for ab to finish
    $stdout = $proc.StandardOutput.ReadToEnd()
    $stderr = $proc.StandardError.ReadToEnd()
    $proc.WaitForExit()
    $sw.Stop()

    $elapsedSec = [math]::Round($sw.Elapsed.TotalSeconds, 2)

    # Save raw report (combine stdout and stderr for full diagnostic fidelity)
    $rawOutput = "=== STDOUT ===`n" + $stdout + "`n=== STDERR ===`n" + $stderr
    $rawOutput | Out-File -FilePath $RawFile -Encoding utf8
    Write-Host "  Raw ab output saved to $RawFile" -ForegroundColor Cyan

    $complete   = 0
    $failed     = 0
    $non2xx     = 0
    $rps        = 0.0
    $totalTime  = $elapsedSec
    $maxLatency = 0.0
    $note       = ""

    if ($stdout -match 'Complete requests:\s+(\d+)') {
        # Standard full ab report
        $complete = [int]$matches[1]

        if ($stdout -match 'Failed requests:\s+(\d+)') {
            $failed = [int]$matches[1]
        }
        if ($stdout -match 'Non-2xx responses:\s+(\d+)') {
            $non2xx = [int]$matches[1]
        }
        if ($stdout -match 'Requests per second:\s+([\d.]+)') {
            $rps = [double]$matches[1]
        }
        if ($stdout -match 'Time taken for tests:\s+([\d.]+)') {
            $totalTime = [double]$matches[1]
        }
        if ($stdout -match '100%\s+(\d+)\s+\(longest request\)') {
            $maxLatency = [double]$matches[1]
        } elseif ($stdout -match 'Total:\s+\S+\s+\S+\s+\S+\s+\S+\s+(\d+)') {
            $maxLatency = [double]$matches[1]
        }
    } elseif ($stdout -match 'Total of (\d+) requests completed' -or $stderr -match 'apr_pollset_poll') {
        # ab timed out due to -s 10 client timeout (apr_pollset_poll 70007)
        if ($stdout -match 'Total of (\d+) requests completed') {
            $complete = [int]$matches[1]
        } else {
            $complete = 0
        }
        $failed     = $n - $complete
        $non2xx     = 0
        $rps        = if ($totalTime -gt 0) { [math]::Round($complete / $totalTime, 2) } else { 0.0 }
        $maxLatency = 10000.0  # Timed out at 10,000 ms client threshold
        $note       = "(Client socket timeout triggered at 10s: $failed requests timed out)"
        Write-Host "  Note: ab hit 10-second client timeout ($failed requests timed out before response)" -ForegroundColor Yellow
    } else {
        Write-Host "`n[ERROR] Unrecognized ab output:" -ForegroundColor Red
        Write-Host $rawOutput
        throw "Failover test failed ($ConfigName): unexpected ab output format."
    }

    # Restart backend2
    Write-Host "  Restarting backend2..." -ForegroundColor DarkGray
    $startResult = Invoke-Docker-Sync "start backend2"
    Write-Host "  backend2 restarted." -ForegroundColor DarkGray

    Write-Host "  Result: Complete=$complete, Failed=$failed, Non-2xx=$non2xx, RPS=$rps, TotalTime=${totalTime}s, MaxLatency=${maxLatency}ms" -ForegroundColor Green

    return [PSCustomObject]@{
        Complete   = $complete
        Failed     = $failed
        Non2xx     = $non2xx
        RPS        = $rps
        TotalTime  = $totalTime
        MaxLatency = $maxLatency
        Note       = $note
    }
}

# ══════════════════════════════════════════════════════════════════════════════
#  MAIN EXECUTION
# ══════════════════════════════════════════════════════════════════════════════
try {
    Write-Host "==========================================================" -ForegroundColor Cyan
    Write-Host " Failover Test: BEFORE vs AFTER Nginx Hardening"            -ForegroundColor Cyan
    Write-Host " Endpoint    : /api/loadtest"                               -ForegroundColor Cyan
    Write-Host " Requests    : $Requests    Concurrency: $Concurrency"      -ForegroundColor Cyan
    Write-Host " Client T/O  : 10 seconds (-s 10)"                          -ForegroundColor Cyan
    Write-Host " Failure     : docker stop backend2 after 5 seconds"        -ForegroundColor Cyan
    Write-Host "==========================================================" -ForegroundColor Cyan

    # Ensure source config files exist
    if (-not (Test-Path "$scriptDir\nginx-before.conf")) {
        throw "nginx-before.conf not found at $scriptDir\nginx-before.conf"
    }
    if (-not (Test-Path "$scriptDir\nginx-after.conf")) {
        throw "nginx-after.conf not found at $scriptDir\nginx-after.conf"
    }

    # ── [1/2] Test BEFORE Configuration ───────────────────────────────────────
    Write-Host "`n[1/2] Running BEFORE test (nginx-before.conf: proxy_next_upstream off)..." -ForegroundColor Yellow
    Copy-Item -Path "$scriptDir\nginx-before.conf" -Destination "$scriptDir\nginx.conf" -Force

    $ErrorActionPreference = "Continue"
    docker compose -f "$scriptDir\docker-compose.yml" down --remove-orphans 2>&1 | Out-Null
    docker compose -f "$scriptDir\docker-compose.yml" up -d 2>&1 | Out-Null
    $ErrorActionPreference = "Stop"

    if (-not (WaitFor-Service)) {
        throw "Stack failed to become ready for BEFORE test."
    }

    Write-Host "  Pausing 5s for connection pool stabilization..." -ForegroundColor Gray
    Start-Sleep -Seconds 5

    $resultBefore = Run-FailoverBenchmark -ConfigName "BEFORE" -n $Requests -c $Concurrency -RawFile "$scriptDir\ab_raw_failover_before.txt"

    # Teardown BEFORE stack
    Write-Host "  Tearing down BEFORE stack..." -ForegroundColor DarkGray
    $ErrorActionPreference = "Continue"
    docker compose -f "$scriptDir\docker-compose.yml" down --remove-orphans 2>&1 | Out-Null
    $ErrorActionPreference = "Stop"

    # ── [2/2] Test AFTER Configuration ────────────────────────────────────────
    Write-Host "`n[2/2] Running AFTER test (nginx-after.conf: hardened failover)..." -ForegroundColor Yellow
    Copy-Item -Path "$scriptDir\nginx-after.conf" -Destination "$scriptDir\nginx.conf" -Force

    $ErrorActionPreference = "Continue"
    docker compose -f "$scriptDir\docker-compose.yml" down --remove-orphans 2>&1 | Out-Null
    docker compose -f "$scriptDir\docker-compose.yml" up -d 2>&1 | Out-Null
    $ErrorActionPreference = "Stop"

    if (-not (WaitFor-Service)) {
        throw "Stack failed to become ready for AFTER test."
    }

    Write-Host "  Pausing 5s for connection pool stabilization..." -ForegroundColor Gray
    Start-Sleep -Seconds 5

    $resultAfter = Run-FailoverBenchmark -ConfigName "AFTER" -n $Requests -c $Concurrency -RawFile "$scriptDir\ab_raw_failover_after.txt"

    # ── Compile Comparison Table ──────────────────────────────────────────────
    Write-Host "`nCompiling comparison results..." -ForegroundColor Yellow

    $rpsDiff   = [math]::Round($resultAfter.RPS - $resultBefore.RPS, 2)
    $timeDiff  = [math]::Round($resultAfter.TotalTime - $resultBefore.TotalTime, 2)
    $latDiff   = [math]::Round($resultAfter.MaxLatency - $resultBefore.MaxLatency, 2)

    $table = @"
================================================================================
FAILOVER TEST COMPARISON: BEFORE vs AFTER NGINX HARDENING
Endpoint        : /api/loadtest
Requests        : $Requests
Concurrency     : $Concurrency
Client Timeout  : 10s (-s 10)
Failure Event   : docker stop backend2 (triggered ~5 seconds after start)
Date/Time       : $(Get-Date -Format "yyyy-MM-dd HH:mm:ss")
================================================================================
Metric                           BEFORE (No Failover)    AFTER (Hardened)        Difference
--------------------------------------------------------------------------------
Complete requests                $($resultBefore.Complete.ToString().PadRight(23)) $($resultAfter.Complete.ToString().PadRight(23)) $($resultAfter.Complete - $resultBefore.Complete)
Failed requests                  $($resultBefore.Failed.ToString().PadRight(23)) $($resultAfter.Failed.ToString().PadRight(23)) $($resultAfter.Failed - $resultBefore.Failed)
Non-2xx responses                $($resultBefore.Non2xx.ToString().PadRight(23)) $($resultAfter.Non2xx.ToString().PadRight(23)) $($resultAfter.Non2xx - $resultBefore.Non2xx)
Requests/sec                     $($resultBefore.RPS.ToString("F2").PadRight(23)) $($resultAfter.RPS.ToString("F2").PadRight(23)) $(if($rpsDiff -ge 0){"+$rpsDiff"}else{"$rpsDiff"})
Total time [s]                   $($resultBefore.TotalTime.ToString("F2").PadRight(23)) $($resultAfter.TotalTime.ToString("F2").PadRight(23)) $(if($timeDiff -ge 0){"+$timeDiff s"}else{"$timeDiff s"})
Max latency [ms]                 $($resultBefore.MaxLatency.ToString("F0").PadRight(23)) $($resultAfter.MaxLatency.ToString("F0").PadRight(23)) $(if($latDiff -ge 0){"+$latDiff ms"}else{"$latDiff ms"})
================================================================================
"@

    Write-Host $table
    $table | Out-File -FilePath "$scriptDir\failover_results.txt" -Encoding utf8
    Write-Host "Results saved to $scriptDir\failover_results.txt" -ForegroundColor Green

} finally {
    # ── Final requirement: leave system running with nginx-after.conf ─────────
    Write-Host "`n[Final Step] Deploying hardened config (nginx-after.conf -> nginx.conf)..." -ForegroundColor Yellow
    if (Test-Path "$scriptDir\nginx-after.conf") {
        Copy-Item -Path "$scriptDir\nginx-after.conf" -Destination "$scriptDir\nginx.conf" -Force
    }
    $ErrorActionPreference = "Continue"
    docker compose -f "$scriptDir\docker-compose.yml" up -d 2>&1 | Out-Null
    Write-Host "Hardened 3-instance stack is now running with nginx-after.conf." -ForegroundColor Green
}
