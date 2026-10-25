/**
 * Normalise le niveau batterie LoRaWAN brut (0–254) en pourcentage 0–100.
 * Spec LoRaWAN : 0 = alimentation externe, 1 = min, 254 = max, 255 = inconnu.
 *
 * Source de vérité unique pour toute l'appli Angular — utilisée par les
 * dashboards (water/gaz/electricity/device-detail) et le service d'export PDF.
 * Miroir de _normalize_battery() dans chatbot/bws_pfe/mcp_client/chart_builder.py —
 * garder les deux synchronisées.
 */
export function normalizeBattery(raw: number | null | undefined): number {
  if (raw == null) return 0;
  if (raw > 100) {
    return Math.round(Math.max(0, Math.min(100, (raw / 254) * 100)) * 10) / 10;
  }
  return Math.max(0, Math.min(100, raw));
}
