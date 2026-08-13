import {
  Component, Input, OnInit, OnDestroy,
  OnChanges, ElementRef, ViewChild, AfterViewInit
} from '@angular/core';
import {
  Chart,
  BarController, DoughnutController, LineController,
  CategoryScale, LinearScale,
  BarElement, ArcElement, PointElement, LineElement,
  Tooltip, Legend
} from 'chart.js';
import { AriaChartConfig } from '../../services/aria.service';
import { ThemeService } from '../../core/services/theme.service';

Chart.register(
  BarController, DoughnutController, LineController,
  CategoryScale, LinearScale,
  BarElement, ArcElement, PointElement, LineElement,
  Tooltip, Legend
);

@Component({
  selector   : 'app-chat-chart',
  templateUrl: './chat-chart.component.html',
  styleUrls  : ['./chat-chart.component.scss'],
})
export class ChatChartComponent implements OnInit, AfterViewInit, OnChanges, OnDestroy {

  @Input() config!: AriaChartConfig;
  @ViewChild('chartCanvas') canvasRef!: ElementRef<HTMLCanvasElement>;

  private chart: Chart | null = null;

  constructor(private theme: ThemeService) {}

  ngOnInit(): void {}

  ngAfterViewInit(): void {
    this._render();
  }

  ngOnChanges(): void {
    if (this.chart) {
      this.chart.destroy();
      this.chart = null;
    }
    if (this.canvasRef) {
      this._render();
    }
  }

  ngOnDestroy(): void {
    this.chart?.destroy();
  }

  private get _isDark(): boolean {
    return this.theme.isDark;
  }

  private _color(index: number, alpha = 1): string {
    const palette = [
      `rgba(14,165,233,${alpha})`,
      `rgba(16,185,129,${alpha})`,
      `rgba(245,158,11,${alpha})`,
      `rgba(231,76,60,${alpha})`,
      `rgba(139,92,246,${alpha})`,
      `rgba(6,182,212,${alpha})`,
      `rgba(249,115,22,${alpha})`,
    ];
    return palette[index % palette.length];
  }

  private _render(): void {
    if (!this.canvasRef || !this.config) return;
    const ctx = this.canvasRef.nativeElement.getContext('2d');
    if (!ctx) return;

    const dark      = this._isDark;
    const gridColor = dark ? 'rgba(255,255,255,0.07)' : 'rgba(0,0,0,0.07)';
    const textColor = dark ? 'rgba(255,255,255,0.5)'  : 'rgba(0,0,0,0.5)';
    const unit      = this.config.unit || '';

    const isLine   = this.config.type === 'line';
    const canvasH  = this.canvasRef.nativeElement.height || 180;

    const chartDatasets = this.config.datasets.map((ds, i) => {
      const perItemColors = (ds as any).colors as string[] | undefined;
      const baseColor     = ds.color || this._color(i);
      const alpha         = this.config.type === 'doughnut' ? 1 : 0.85;
      const borderColor   = perItemColors
        ? perItemColors
        : baseColor.startsWith('rgba') ? baseColor : this._hexToRgba(baseColor, 1);

      return {
        label          : ds.label,
        data           : ds.data,
        backgroundColor: perItemColors
          ? perItemColors
          : this.config.type === 'doughnut'
            ? this.config.labels.map((_, j) => this._color(j))
            : isLine
              ? this._lineGradient(ctx, baseColor, canvasH)
              : baseColor.startsWith('rgba') ? baseColor : this._hexToRgba(baseColor, alpha),
        borderColor    : borderColor,
        borderWidth    : this.config.type === 'doughnut' ? 2 : isLine ? 2.5 : 1.5,
        borderRadius   : this.config.type === 'bar' ? 4 : 0,
        pointRadius    : isLine ? (this.config.labels.length > 30 ? 0 : 3) : undefined,
        pointHoverRadius: isLine ? 5 : undefined,
        pointBackgroundColor: isLine ? borderColor : undefined,
        pointBorderColor: isLine ? (dark ? '#0b1220' : '#ffffff') : undefined,
        pointBorderWidth: isLine ? 1.5 : undefined,
        tension        : 0.4,
        fill           : isLine ? 'origin' : false,
      };
    });

    const scales: any = this.config.type !== 'doughnut' ? {
      x: {
        grid  : { color: gridColor, drawBorder: false },
        ticks : { color: textColor, font: { size: 10 }, maxRotation: 35 },
      },
      y: {
        grid   : { color: gridColor, drawBorder: false },
        ticks  : {
          color   : textColor,
          font    : { size: 10 },
          callback: (v: number) => unit ? `${v} ${unit}` : v,
        },
        beginAtZero: true,
        ...(this.config.yMax != null ? { max: this.config.yMax } : {}),
      },
    } : undefined;

    this.chart = new Chart(ctx, {
      type: this.config.type as any,
      data: { labels: this.config.labels, datasets: chartDatasets },
      options: {
        responsive         : true,
        maintainAspectRatio: false,
        animation          : { duration: 400 },
        plugins: {
          legend: {
            display : this.config.type === 'doughnut' || (isLine && chartDatasets.length > 1),
            position: 'bottom',
            labels  : { color: textColor, font: { size: 10 }, padding: 8, boxWidth: 10 },
          },
          tooltip: {
            backgroundColor: dark ? 'rgba(6,12,26,0.95)' : 'rgba(255,255,255,0.97)',
            titleColor     : dark ? '#e2e8f0' : '#1e293b',
            bodyColor      : dark ? '#94a3b8' : '#475569',
            borderColor    : dark ? 'rgba(255,255,255,0.1)' : 'rgba(0,0,0,0.1)',
            borderWidth    : 1,
            padding        : 8,
            callbacks      : {
              label: (ctx: any) => {
                const v = ctx.parsed.y ?? ctx.parsed;
                return unit ? ` ${v} ${unit}` : ` ${v}`;
              },
            },
          },
        },
        ...(scales ? { scales } : {}),
      },
    });
  }

  private _lineGradient(ctx: CanvasRenderingContext2D, color: string, height: number): CanvasGradient {
    const gradient = ctx.createLinearGradient(0, 0, 0, height);
    gradient.addColorStop(0, this._toRgba(color, 0.35));
    gradient.addColorStop(1, this._toRgba(color, 0.02));
    return gradient;
  }

  private _toRgba(color: string, alpha: number): string {
    return color.startsWith('rgba')
      ? color.replace(/,\s*[\d.]+\)$/, `, ${alpha})`)
      : this._hexToRgba(color, alpha);
  }

  private _hexToRgba(hex: string, alpha: number): string {
    const r = parseInt(hex.slice(1, 3), 16);
    const g = parseInt(hex.slice(3, 5), 16);
    const b = parseInt(hex.slice(5, 7), 16);
    return `rgba(${r},${g},${b},${alpha})`;
  }
}
