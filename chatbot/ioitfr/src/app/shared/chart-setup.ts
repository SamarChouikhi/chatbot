import {
  Chart,
  LineController, BarController, DoughnutController, RadarController,
  CategoryScale, LinearScale, RadialLinearScale,
  PointElement, LineElement, BarElement, ArcElement,
  Tooltip, Legend, Filler
} from 'chart.js';

// Enregistrement unique des contrôleurs Chart.js utilisés par les dashboards domaine.
// Importé pour son effet de bord par domain-dashboard.base.ts.
Chart.register(
  LineController, BarController, DoughnutController, RadarController,
  CategoryScale, LinearScale, RadialLinearScale,
  PointElement, LineElement, BarElement, ArcElement,
  Tooltip, Legend, Filler
);

/** Couleurs neutres communes à tous les graphiques sur fond sombre. */
export const CHART_BASE = {
  grid:    'rgba(255,255,255,0.06)',
  text:    'rgba(255,255,255,0.45)',
  tooltip: 'rgba(6,12,26,0.95)',
} as const;
