$f = 'd:\PFE\chatbot\ioitfr\src\app\dashboard\dashboard.component.ts'
$c = Get-Content $f -Raw

# Supprimer les variables isRefreshing, lastRefreshed, _last*, lastRefreshedLabel
$c = $c -replace '\s*isRefreshing\s*=\s*false;', ''
$c = $c -replace '\s*lastRefreshed:\s*Date \| null = null;', ''
$c = $c -replace '\s*private _lastWaterM3\s*=\s*0;', ''
$c = $c -replace '\s*private _lastAlerts\s*=\s*0;', ''
$c = $c -replace '\s*private _lastElecKwh\s*=\s*0;', ''
$c = $c -replace '\s*private _lastGazL\s*=\s*0;', ''
$c = $c -replace '\s*private refreshInterval:\s*any;', ''

# Supprimer le getter lastRefreshedLabel
$c = [regex]::Replace($c, '(?s)\s*get lastRefreshedLabel\(\).*?}\s*}', '}', [System.Text.RegularExpressions.RegexOptions]::Singleline)

# Supprimer startAutoRefresh() et silentCheck() et refreshAll()
$c = [regex]::Replace($c, '(?s)\s*private startAutoRefresh\(\).*?}\s*private silentCheck\(\).*?}\s*}\s*refreshAll\(\).*?}\s*}', '', [System.Text.RegularExpressions.RegexOptions]::Singleline)

# Supprimer les appels dans ngOnInit et ngOnDestroy
$c = $c -replace '\s*this\.startAutoRefresh\(\);', ''
$c = $c -replace '\s*setTimeout\(\(\) => \{ if \(!this\.lastRefreshed\) this\.lastRefreshed = new Date\(\); \}, 3000\);', ''
$c = $c -replace '\s*if \(this\.refreshInterval\)\s*clearInterval\(this\.refreshInterval\);', ''

Set-Content $f $c -Encoding UTF8
Write-Host "Done"
