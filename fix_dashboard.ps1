$f = 'd:\PFE\chatbot\ioitfr\src\app\dashboard\dashboard.component.ts'
$c = Get-Content $f -Raw

# Remplacer le bloc corrompu (startAutoRefresh avec \n litteraux)
$old = '  private startAutoRefresh\(\): void \{\\n.*?loadFuelDataCb\(done\);\\n  \}'
$new = '  private startAutoRefresh(): void {
    this.refreshInterval = setInterval(() => this.silentCheck(), 5 * 60 * 1000);
  }

  private silentCheck(): void {
    if (this.isRefreshing) return;
    this.waterSvc.getAlerts().subscribe({
      next: (alerts) => { if (alerts.length !== this._lastAlerts) this.refreshAll(); },
      error: () => {}
    });
  }

  refreshAll(): void {
    if (this.isRefreshing) return;
    this.isRefreshing = true;
    this.alertCount = 0; this.alertsExcessive = 0; this.alertsHigh = 0; this.alertsLow = 0;
    let pending = 4;
    const done = () => {
      if (--pending === 0) {
        this.isRefreshing = false; this.lastRefreshed = new Date();
        this._lastAlerts = this.globalAlerts; this._lastWaterM3 = this.waterM3Total;
        this._lastElecKwh = this.elecKwhTotal; this._lastGazL = this.gazLTotal;
      }
    };
    this.loadGazDataCb(done); this.loadElecDataCb(done);
    this.loadWaterDataCb(done); this.loadFuelDataCb(done);
  }'

$c = [regex]::Replace($c, $old, $new, [System.Text.RegularExpressions.RegexOptions]::Singleline)
Set-Content $f $c -Encoding UTF8
Write-Host "Done"
