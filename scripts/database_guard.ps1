function Get-ProtectedDatabaseState {
    param([string[]]$DatabasePaths)

    $state = @{}
    foreach ($databasePath in $DatabasePaths) {
        $fullDatabasePath = [IO.Path]::GetFullPath($databasePath)
        $candidates = @($fullDatabasePath)
        foreach ($suffix in @("-wal", "-shm", "-journal")) {
            $candidates += $fullDatabasePath + $suffix
        }

        foreach ($candidate in $candidates) {
            if (Test-Path -LiteralPath $candidate) {
                $item = Get-Item -LiteralPath $candidate
                $hash = (Get-FileHash -LiteralPath $candidate -Algorithm SHA256).Hash
                $state[$candidate] = "present|$($item.Length)|$($item.LastWriteTimeUtc.Ticks)|$hash"
            }
            else {
                $state[$candidate] = "absent"
            }
        }
    }
    return $state
}

function Assert-ProtectedDatabaseStateUnchanged {
    param([hashtable]$Before, [hashtable]$After)

    $changed = @(
        ($Before.Keys + $After.Keys) |
            Sort-Object -Unique |
            Where-Object { $Before[$_] -cne $After[$_] }
    )
    if ($changed.Count -gt 0) {
        throw "Verification đã làm thay đổi DB/sidecar được bảo vệ: $($changed -join ', ')"
    }
}
