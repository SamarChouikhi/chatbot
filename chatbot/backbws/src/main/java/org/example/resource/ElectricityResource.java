package org.example.resource;

import jakarta.inject.Inject;
import jakarta.ws.rs.*;
import jakarta.ws.rs.core.MediaType;
import jakarta.ws.rs.core.Response;
import org.example.dto.ElectricityDto.*;
import org.example.service.ElectricityService;

import java.time.LocalDateTime;
import java.time.format.DateTimeParseException;
import java.util.List;

/**
 * REST Resource — Module Électricité
 *
 * Base URL : /api/electricity
 *
 * ┌──────────────────────────────────────────────────────────────────────────┐
 * │ GET /api/electricity/realtime                → tous les devices (RT)     │
 * │ GET /api/electricity/realtime/{id}           → un device (RT)            │
 * │ GET /api/electricity/realtime/alerts/battery → batterie faible           │
 * │ GET /api/electricity/realtime/alerts/thd     → THD élevé                 │
 * │ GET /api/electricity/realtime/alerts/cosfi   → cosfi faible              │
 * │                                                                          │
 * │ GET /api/electricity/raw?device=&from=&to=   → mesures brutes            │
 * │ GET /api/electricity/raw/{id}/latest         → dernière mesure brute     │
 * │                                                                          │
 * │ GET /api/electricity/hourly?device=&from=&to=  → agrégats horaires       │
 * │ GET /api/electricity/daily?device=&from=&to=   → agrégats journaliers    │
 * │ GET /api/electricity/monthly/{id}              → tout l'historique mensuel│
 * │ GET /api/electricity/monthly?device=&from=&to= → mensuel filtré          │
 * │                                                                          │
 * │ GET /api/electricity/summary/{id}?from=&to= → résumé + CO2 + coût       │
 * │ GET /api/electricity/summary?from=&to=      → résumé tous devices        │
 * │                                                                          │
 * │ GET /api/electricity/chart/hourly/{id}?from=&to=   → chart horaire       │
 * │ GET /api/electricity/chart/daily/{id}?from=&to=    → chart journalier    │
 * │ GET /api/electricity/chart/monthly/{id}?from=&to=  → chart mensuel       │
 * │                                                                          │
 * │ GET /api/electricity/quality/daily/{id}?from=&to=   → qualité journalier │
 * │ GET /api/electricity/quality/monthly/{id}?from=&to= → qualité mensuel    │
 * │                                                                          │
 * │ GET /api/electricity/alerts                 → toutes alertes actives     │
 * │ GET /api/electricity/compare/{id}?from=&to= → comparaison périodes       │
 * │ GET /api/electricity/config/{id}            → config init_energy          │
 * └──────────────────────────────────────────────────────────────────────────┘
 */
@Path("/api/electricity")
@Produces(MediaType.APPLICATION_JSON)
@Consumes(MediaType.APPLICATION_JSON)
public class ElectricityResource {

    @Inject
    ElectricityService electricityService;

    // ═══════════════════════════════════════════════════════════════════════════
    // TEMPS RÉEL
    // ═══════════════════════════════════════════════════════════════════════════

    @GET
    @Path("/realtime")
    public Response getAllRealTime() {
        List<RtEnPDto> list = electricityService.getAllRealTime();
        return Response.ok(list).build();
    }

    @GET
    @Path("/realtime/{idDevice}")
    public Response getRealTime(@PathParam("idDevice") Integer idDevice) {
        RtEnPDto dto = electricityService.getRealTime(idDevice);
        if (dto == null) return notFound("Compteur électricité introuvable : " + idDevice);
        return Response.ok(dto).build();
    }

    @GET
    @Path("/realtime/alerts/battery")
    public Response getDevicesWithLowBattery() {
        return Response.ok(electricityService.getDevicesWithLowBattery()).build();
    }

    @GET
    @Path("/realtime/alerts/thd")
    public Response getDevicesWithHighTHD() {
        return Response.ok(electricityService.getDevicesWithHighTHD()).build();
    }

    @GET
    @Path("/realtime/alerts/cosfi")
    public Response getDevicesWithLowCosfi() {
        return Response.ok(electricityService.getDevicesWithLowCosfi()).build();
    }

    // ═══════════════════════════════════════════════════════════════════════════
    // BRUT (archive_en_p)
    // ═══════════════════════════════════════════════════════════════════════════

    /**
     * GET /api/electricity/raw?device=1001&from=2025-09-01T00:00:00&to=2025-09-01T12:00:00
     * Si device absent → tous les devices
     */
    @GET
    @Path("/raw")
    public Response getRaw(
            @QueryParam("device") Integer idDevice,
            @QueryParam("from")   String  fromStr,
            @QueryParam("to")     String  toStr) {

        DateRange range = parseDateRange(fromStr, toStr, 1);
        if (range == null) return badRequest("Paramètres from/to invalides.");

        if (idDevice != null) {
            return Response.ok(electricityService.getRawByDeviceAndPeriod(idDevice, range.from, range.to)).build();
        }
        return Response.ok(electricityService.getAllRawByPeriod(range.from, range.to)).build();
    }

    @GET
    @Path("/raw/{idDevice}/latest")
    public Response getLatestRaw(@PathParam("idDevice") Integer idDevice) {
        var dto = electricityService.getLatestRaw(idDevice);
        if (dto == null) return notFound("Aucune donnée brute pour ce device.");
        return Response.ok(dto).build();
    }

    // ═══════════════════════════════════════════════════════════════════════════
    // HORAIRE (archive_en_p_h)
    // ═══════════════════════════════════════════════════════════════════════════

    /**
     * GET /api/electricity/hourly?device=1001&from=2025-09-01T00:00:00&to=2025-09-07T00:00:00
     */
    @GET
    @Path("/hourly")
    public Response getHourly(
            @QueryParam("device") Integer idDevice,
            @QueryParam("from")   String  fromStr,
            @QueryParam("to")     String  toStr) {

        DateRange range = parseDateRange(fromStr, toStr, 24);
        if (range == null) return badRequest("Paramètres from/to invalides.");

        if (idDevice != null) {
            return Response.ok(electricityService.getHourlyByDeviceAndPeriod(idDevice, range.from, range.to)).build();
        }
        return Response.ok(electricityService.getAllHourlyByPeriod(range.from, range.to)).build();
    }

    // ═══════════════════════════════════════════════════════════════════════════
    // JOURNALIER (archive_en_p_j)
    // ═══════════════════════════════════════════════════════════════════════════

    /**
     * GET /api/electricity/daily?device=1001&from=2025-09-01T00:00:00&to=2025-09-30T00:00:00
     */
    @GET
    @Path("/daily")
    public Response getDaily(
            @QueryParam("device") Integer idDevice,
            @QueryParam("from")   String  fromStr,
            @QueryParam("to")     String  toStr) {

        DateRange range = parseDateRange(fromStr, toStr, 24 * 30);
        if (range == null) return badRequest("Paramètres from/to invalides.");

        if (idDevice != null) {
            return Response.ok(electricityService.getDailyByDeviceAndPeriod(idDevice, range.from, range.to)).build();
        }
        return Response.ok(electricityService.getAllDailyByPeriod(range.from, range.to)).build();
    }

    // ═══════════════════════════════════════════════════════════════════════════
    // MENSUEL (archive_en_p_m)
    // ═══════════════════════════════════════════════════════════════════════════

    /**
     * GET /api/electricity/monthly/{idDevice}             → tout l'historique mensuel
     * GET /api/electricity/monthly?device=&from=&to=      → filtré par période
     */
    @GET
    @Path("/monthly/{idDevice}")
    public Response getMonthlyByDevice(@PathParam("idDevice") Integer idDevice) {
        return Response.ok(electricityService.getMonthlyByDevice(idDevice)).build();
    }

    @GET
    @Path("/monthly")
    public Response getMonthly(
            @QueryParam("device") Integer idDevice,
            @QueryParam("from")   String  fromStr,
            @QueryParam("to")     String  toStr) {

        DateRange range = parseDateRange(fromStr, toStr, 24 * 365);
        if (range == null) return badRequest("Paramètres from/to invalides.");

        if (idDevice != null) {
            return Response.ok(electricityService.getMonthlyByDeviceAndPeriod(idDevice, range.from, range.to)).build();
        }
        return Response.ok(electricityService.getAllMonthlyByPeriod(range.from, range.to)).build();
    }

    // ═══════════════════════════════════════════════════════════════════════════
    // RÉSUMÉ / DASHBOARD
    // ═══════════════════════════════════════════════════════════════════════════

    /**
     * GET /api/electricity/summary/1001?from=2025-09-01T00:00:00&to=2026-01-31T00:00:00
     */
    @GET
    @Path("/summary/{idDevice}")
    public Response getSummary(
            @PathParam("idDevice") Integer idDevice,
            @QueryParam("from")    String  fromStr,
            @QueryParam("to")      String  toStr) {

        DateRange range = parseDateRange(fromStr, toStr, 24 * 30);
        if (range == null) return badRequest("Paramètres from/to invalides.");
        return Response.ok(electricityService.getSummary(idDevice, range.from, range.to)).build();
    }

    /**
     * GET /api/electricity/summary?from=2025-09-01T00:00:00&to=2026-01-31T00:00:00
     */
    @GET
    @Path("/summary")
    public Response getAllSummaries(
            @QueryParam("from") String fromStr,
            @QueryParam("to")   String toStr) {

        DateRange range = parseDateRange(fromStr, toStr, 24 * 30);
        if (range == null) return badRequest("Paramètres from/to invalides.");
        return Response.ok(electricityService.getAllSummaries(range.from, range.to)).build();
    }

    // ═══════════════════════════════════════════════════════════════════════════
    // CHART DATA
    // ═══════════════════════════════════════════════════════════════════════════

    /**
     * GET /api/electricity/chart/hourly/1001?from=2025-09-01T00:00:00&to=2025-09-02T00:00:00
     */
    @GET
    @Path("/chart/hourly/{idDevice}")
    public Response getHourlyChart(
            @PathParam("idDevice") Integer idDevice,
            @QueryParam("from")    String  fromStr,
            @QueryParam("to")      String  toStr) {

        DateRange range = parseDateRange(fromStr, toStr, 24);
        if (range == null) return badRequest("Paramètres from/to invalides.");
        return Response.ok(electricityService.getHourlyChart(idDevice, range.from, range.to)).build();
    }

    /**
     * GET /api/electricity/chart/daily/1001?from=2025-09-01T00:00:00&to=2025-09-30T00:00:00
     */
    @GET
    @Path("/chart/daily/{idDevice}")
    public Response getDailyChart(
            @PathParam("idDevice") Integer idDevice,
            @QueryParam("from")    String  fromStr,
            @QueryParam("to")      String  toStr) {

        DateRange range = parseDateRange(fromStr, toStr, 24 * 30);
        if (range == null) return badRequest("Paramètres from/to invalides.");
        return Response.ok(electricityService.getDailyChart(idDevice, range.from, range.to)).build();
    }

    /**
     * GET /api/electricity/chart/monthly/1001?from=2025-09-01T00:00:00&to=2026-01-31T00:00:00
     */
    @GET
    @Path("/chart/monthly/{idDevice}")
    public Response getMonthlyChart(
            @PathParam("idDevice") Integer idDevice,
            @QueryParam("from")    String  fromStr,
            @QueryParam("to")      String  toStr) {

        DateRange range = parseDateRange(fromStr, toStr, 24 * 365);
        if (range == null) return badRequest("Paramètres from/to invalides.");
        return Response.ok(electricityService.getMonthlyChart(idDevice, range.from, range.to)).build();
    }

    // ═══════════════════════════════════════════════════════════════════════════
    // QUALITÉ RÉSEAU
    // ═══════════════════════════════════════════════════════════════════════════

    /**
     * GET /api/electricity/quality/daily/1001?from=2025-09-01T00:00:00&to=2025-09-30T00:00:00
     */
    @GET
    @Path("/quality/daily/{idDevice}")
    public Response getPowerQualityDaily(
            @PathParam("idDevice") Integer idDevice,
            @QueryParam("from")    String  fromStr,
            @QueryParam("to")      String  toStr) {

        DateRange range = parseDateRange(fromStr, toStr, 24 * 30);
        if (range == null) return badRequest("Paramètres from/to invalides.");
        return Response.ok(electricityService.getPowerQualityDaily(idDevice, range.from, range.to)).build();
    }

    /**
     * GET /api/electricity/quality/monthly/1001?from=2025-09-01T00:00:00&to=2026-01-31T00:00:00
     */
    @GET
    @Path("/quality/monthly/{idDevice}")
    public Response getPowerQualityMonthly(
            @PathParam("idDevice") Integer idDevice,
            @QueryParam("from")    String  fromStr,
            @QueryParam("to")      String  toStr) {

        DateRange range = parseDateRange(fromStr, toStr, 24 * 365);
        if (range == null) return badRequest("Paramètres from/to invalides.");
        return Response.ok(electricityService.getPowerQualityMonthly(idDevice, range.from, range.to)).build();
    }

    // ═══════════════════════════════════════════════════════════════════════════
    // ALERTES
    // ═══════════════════════════════════════════════════════════════════════════

    /** GET /api/electricity/alerts */
    @GET
    @Path("/alerts")
    public Response getAlerts() {
        return Response.ok(electricityService.getActiveAlerts()).build();
    }

    // ═══════════════════════════════════════════════════════════════════════════
    // COMPARAISON
    // ═══════════════════════════════════════════════════════════════════════════

    /**
     * GET /api/electricity/compare/1001?from=2025-12-01T00:00:00&to=2025-12-31T00:00:00
     */
    @GET
    @Path("/compare/{idDevice}")
    public Response compare(
            @PathParam("idDevice") Integer idDevice,
            @QueryParam("from")    String  fromStr,
            @QueryParam("to")      String  toStr) {

        DateRange range = parseDateRange(fromStr, toStr, 24 * 30);
        if (range == null) return badRequest("Paramètres from/to invalides.");
        return Response.ok(electricityService.compareWithPreviousPeriod(idDevice, range.from, range.to)).build();
    }

    // ═══════════════════════════════════════════════════════════════════════════
    // CONFIG (init_energy)
    // ═══════════════════════════════════════════════════════════════════════════

    /** GET /api/electricity/config/1001 */
    @GET
    @Path("/config/{idDevice}")
    public Response getConfig(@PathParam("idDevice") Integer idDevice) {
        var dto = electricityService.getConfig(idDevice);
        if (dto == null) return notFound("Configuration introuvable pour le device " + idDevice);
        return Response.ok(dto).build();
    }

    // ═══════════════════════════════════════════════════════════════════════════
    // HELPERS INTERNES
    // ═══════════════════════════════════════════════════════════════════════════

    private static class DateRange {
        LocalDateTime from;
        LocalDateTime to;
        DateRange(LocalDateTime f, LocalDateTime t) { from = f; to = t; }
    }

    private DateRange parseDateRange(String fromStr, String toStr, int defaultHours) {
        try {
            LocalDateTime from = fromStr != null
                    ? LocalDateTime.parse(fromStr)
                    : LocalDateTime.now().minusHours(defaultHours);
            LocalDateTime to   = toStr != null
                    ? LocalDateTime.parse(toStr)
                    : LocalDateTime.now();
            return new DateRange(from, to);
        } catch (DateTimeParseException e) {
            return null;
        }
    }

    private Response notFound(String msg) {
        return Response.status(Response.Status.NOT_FOUND)
                .entity("{\"error\":\"" + msg + "\"}")
                .build();
    }

    private Response badRequest(String msg) {
        return Response.status(Response.Status.BAD_REQUEST)
                .entity("{\"error\":\"" + msg + "\"}")
                .build();
    }
}
