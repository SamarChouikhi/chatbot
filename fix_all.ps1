$ts  = 'd:\PFE\chatbot\ioitfr\src\app\dashboard\dashboard.component.ts'
$html = 'd:\PFE\chatbot\ioitfr\src\app\dashboard\dashboard.component.html'

# ── 1. CORRIGER LE TS ─────────────────────────────────────────
$c = Get-Content $ts -Raw

# Supprimer les variables refresh
$c = $c -replace '\s*isRefreshing\s*=\s*false;', ''
$c = $c -replace '\s*lastRefreshed:\s*Date \| null = null;', ''
$c = $c -replace '\s*refreshCountdown\s*=\s*30;', ''
$c = $c -replace '\s*secondsSinceRefresh\s*=\s*0;', ''
$c = $c -replace '\s*private refreshInterval:\s*any;', ''
$c = $c -replace '\s*private countdownInterval:\s*any;', ''

# Supprimer le getter lastRefreshedLabel
$c = [regex]::Replace($c, '\s*get lastRefreshedLabel\(\): string \{[^}]+\}', '', [System.Text.RegularExpressions.RegexOptions]::Singleline)

# Supprimer startAutoRefresh() complet
$c = [regex]::Replace($c, '\s*private startAutoRefresh\(\): void \{[^}]+\}', '', [System.Text.RegularExpressions.RegexOptions]::Singleline)

# Supprimer refreshAll() complet
$c = [regex]::Replace($c, '\s*refreshAll\(\): void \{.*?this\.loadFuelDataCb\(done\);\s*\}', '', [System.Text.RegularExpressions.RegexOptions]::Singleline)

# Supprimer les appels dans ngOnInit/ngOnDestroy
$c = $c -replace '\s*this\.startAutoRefresh\(\);', ''
$c = $c -replace '\s*if \(this\.refreshInterval\)\s*clearInterval\(this\.refreshInterval\);', ''
$c = $c -replace '\s*if \(this\.countdownInterval\)\s*clearInterval\(this\.countdownInterval\);', ''
$c = $c -replace '\s*setTimeout\(\(\) => \{ if \(!this\.lastRefreshed\) this\.lastRefreshed = new Date\(\); \}, 3000\);', ''

Set-Content $ts $c -Encoding UTF8
Write-Host "TS corrige"

# ── 2. CORRIGER LE HTML ───────────────────────────────────────
$h = Get-Content $html -Raw

# Supprimer profile-role dans la topbar
$h = $h -replace '\s*<span class="profile-role">\{\{ userRole \}\}</span>', ''

# Supprimer le bloc modules-grid (display:none)
$h = [regex]::Replace($h, '(?s)\s*<div class="modules-grid" style="display:none">.*?</div><!-- /modules-grid -->', '', [System.Text.RegularExpressions.RegexOptions]::Singleline)

Set-Content $html $h -Encoding UTF8
Write-Host "HTML corrige"
Write-Host "Termine !"
