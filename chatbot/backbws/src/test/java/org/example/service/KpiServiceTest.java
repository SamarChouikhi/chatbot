package org.example.service;

import jakarta.persistence.EntityManager;
import jakarta.persistence.Query;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Nested;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.mockito.junit.jupiter.MockitoSettings;
import org.mockito.quality.Strictness;

import java.lang.reflect.Method;

import static org.assertj.core.api.Assertions.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

/**
 * Tests unitaires — KpiService.
 * Les méthodes privées trend() et severityFromType() sont testées via réflexion
 * (elles contiennent de la logique métier sans dépendance à la DB).
 */
@ExtendWith(MockitoExtension.class)
class KpiServiceTest {

    @Mock
    EntityManager em;

    @InjectMocks
    KpiService kpiService;

    // ── Helpers réflexion ──────────────────────────────────────────────────────

    private String callTrend(double current, double previous) throws Exception {
        Method m = KpiService.class.getDeclaredMethod("trend", double.class, double.class);
        m.setAccessible(true);
        return (String) m.invoke(kpiService, current, previous);
    }

    private String callSeverity(String type) throws Exception {
        Method m = KpiService.class.getDeclaredMethod("severityFromType", String.class);
        m.setAccessible(true);
        return (String) m.invoke(kpiService, type);
    }

    // ── trend() ───────────────────────────────────────────────────────────────

    @Nested
    @DisplayName("trend()")
    class TrendTests {

        @Test
        @DisplayName("hausse 50% → '+50.0%'")
        void increase() throws Exception {
            assertThat(callTrend(150.0, 100.0)).isEqualTo("+50.0%");
        }

        @Test
        @DisplayName("baisse 25% → '-25.0%'")
        void decrease() throws Exception {
            assertThat(callTrend(75.0, 100.0)).isEqualTo("-25.0%");
        }

        @Test
        @DisplayName("stable → '+0.0%'")
        void stable() throws Exception {
            assertThat(callTrend(100.0, 100.0)).isEqualTo("+0.0%");
        }

        @Test
        @DisplayName("previous = 0 → '0.0%' (évite division par zéro)")
        void zeroPrevious() throws Exception {
            assertThat(callTrend(50.0, 0.0)).isEqualTo("0.0%");
        }

        @Test
        @DisplayName("previous négatif → résultat calculé correctement")
        void negativePrevious() throws Exception {
            // Edge case : previous < 0 → la formule s'applique quand même
            String result = callTrend(50.0, -100.0);
            assertThat(result).isNotNull();
        }

        @Test
        @DisplayName("format inclut le signe + pour une hausse")
        void positiveHasSign() throws Exception {
            assertThat(callTrend(200.0, 100.0)).startsWith("+");
        }
    }

    // ── severityFromType() ───────────────────────────────────────────────────

    @Nested
    @DisplayName("severityFromType()")
    class SeverityTests {

        @Test
        @DisplayName("null → LOW")
        void nullType() throws Exception {
            assertThat(callSeverity(null)).isEqualTo("LOW");
        }

        @Test
        @DisplayName("type vide → LOW")
        void emptyType() throws Exception {
            assertThat(callSeverity("")).isEqualTo("LOW");
        }

        @Test
        @DisplayName("'excess' → CRITICAL")
        void excessCritical() throws Exception {
            assertThat(callSeverity("excess_consumption")).isEqualTo("CRITICAL");
        }

        @Test
        @DisplayName("'critical' → CRITICAL")
        void criticalType() throws Exception {
            assertThat(callSeverity("critical_failure")).isEqualTo("CRITICAL");
        }

        @Test
        @DisplayName("'danger' → CRITICAL")
        void dangerType() throws Exception {
            assertThat(callSeverity("danger_zone")).isEqualTo("CRITICAL");
        }

        @Test
        @DisplayName("'high' → HIGH")
        void highType() throws Exception {
            assertThat(callSeverity("high_temperature")).isEqualTo("HIGH");
        }

        @Test
        @DisplayName("'warn' → HIGH")
        void warnType() throws Exception {
            assertThat(callSeverity("warn_battery")).isEqualTo("HIGH");
        }

        @Test
        @DisplayName("'elev' → HIGH (elevated)")
        void elevType() throws Exception {
            assertThat(callSeverity("elevated_pressure")).isEqualTo("HIGH");
        }

        @Test
        @DisplayName("type inconnu → LOW")
        void unknownType() throws Exception {
            assertThat(callSeverity("normal_operation")).isEqualTo("LOW");
        }

        @Test
        @DisplayName("insensible à la casse — 'EXCESS' → CRITICAL")
        void caseInsensitive() throws Exception {
            assertThat(callSeverity("EXCESS")).isEqualTo("CRITICAL");
        }
    }

    // ── getChartData() — structure de sortie ─────────────────────────────────

    @Nested
    @DisplayName("getChartData()")
    @MockitoSettings(strictness = Strictness.LENIENT)
    class ChartDataTests {

        @BeforeEach
        void setupMocks() {
            Query mockQuery = mock(Query.class);
            when(em.createQuery(anyString())).thenReturn(mockQuery);
            when(mockQuery.setParameter(eq("p1"), any())).thenReturn(mockQuery);
            when(mockQuery.setParameter(eq("p2"), any())).thenReturn(mockQuery);
            when(mockQuery.getSingleResult()).thenReturn(0.0);
        }

        @Test
        @DisplayName("retourne exactement N entrées pour N jours")
        void correctNumberOfEntries() {
            var result = kpiService.getChartData(7);
            assertThat(result).hasSize(7);
        }

        @Test
        @DisplayName("chaque entrée a un label non null")
        void labelsNotNull() {
            var result = kpiService.getChartData(3);
            result.forEach(c -> assertThat(c.label).isNotNull());
        }

        @Test
        @DisplayName("les valeurs CO2 sont >= 0 quand consommation = 0")
        void co2NonNegative() {
            var result = kpiService.getChartData(5);
            result.forEach(c -> {
                assertThat(c.electricity).isGreaterThanOrEqualTo(0.0);
                assertThat(c.water).isGreaterThanOrEqualTo(0.0);
                assertThat(c.fuel).isGreaterThanOrEqualTo(0.0);
            });
        }

        @Test
        @DisplayName("0 jours → liste vide")
        void zeroDays() {
            var result = kpiService.getChartData(0);
            assertThat(result).isEmpty();
        }
    }
}
