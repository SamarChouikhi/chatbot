package org.example.resource;

import jakarta.inject.Inject;
import jakarta.ws.rs.*;
import jakarta.ws.rs.core.MediaType;
import jakarta.ws.rs.core.Response;
import org.example.dto.WaterDto.*;
import org.example.service.WaterService;

import java.time.LocalDateTime;
import java.time.format.DateTimeParseException;
import java.util.List;

/**
 * REST Resource — Module Eau (WM)
 *
 * Base URL : /api/water
 *
 * ┌──────────────────────────────────────────────────────────────────────┐
 * │ GET /api/water/realtime                → tous les devices (RT)       │
 * │ GET /api/water/realtime/{id}           → un device (RT)              │
 * │ GET /api/water/realtime/alerts         → devices en alerte           │
 * │ GET /api/water/realtime/leaks          → devices avec fuite          │
 * │                                                                      │
 * │ GET /api/water/raw?device=&from=&to=   → données brutes              │
 * │ GET /api/water/raw/{id}/latest         → dernière mesure brute       │
 * │                                                                      │
 * │ GET /api/water/hourly?device=&from=&to=   → agrégats horaires        │
 * │ GET /api/water/daily?device=&from=&to=    → agrégats journaliers     │
 * │ GET /api/water/monthly?device=&from=&to=  → agrégats mensuels        │
 * │ GET /api/water/monthly/{id}               → tout l'historique mensuel│
 * │                                                                      │
 * │ GET /api/water/summary/{id}?from=&to=  → résumé + CO2 + coût        │
 * │ GET /api/water/summary?from=&to=       → résumé tous devices         │
 * │                                                                      │
 * │ GET /api/water/chart/hourly/{id}?from=&to=   → chart horaire         │
 * │ GET /api/water/chart/daily/{id}?from=&to=    → chart journalier      │
 * │ GET /api/water/chart/monthly/{id}?from=&to=  → chart mensuel         │
 * │                                                                      │
 * │ GET /api/water/stats/{id}?from=&to=    → statistiques avancées       │
 * │ GET /api/water/stats?from=&to=         → stats tous devices          │
 * │                                                                      │
 * │ GET /api/water/alerts                  → toutes alertes actives      │
 * │ GET /api/water/compare/{id}?from=&to=  → comparaison période préc.  │
 * │                                                                      │
 * │ GET /api/water/config/{id}             → config init_wm d'un device  │
 * └──────────────────────────────────────────────────────────────────────┘
 */
@Path("/api/water")
@Produces(MediaType.APPLICATION_JSON)
@Consumes(MediaType.APPLICATION_JSON)
public class WaterResource {

    @Inject
    WaterService waterService;

    // ═══════════════════════════════════════════════════════════════════════════
    // TEMPS RÉEL
    // ═══════════════════════════════════════════════════════════════════════════

    @GET
    @Path("/realtime")
    public Response getAllRealTime() {
        List<RtWmDto> list = waterService.getAllRealTime();
        return Response.ok(list).build();
    }

    @GET
    @Path("/realtime/{idDevice}")
    public Response getRealTime(@PathParam("idDevice") Integer idDevice) {
        RtWmDto dto = waterService.getRealTime(idDevice);
        if (dto == null) return notFound("Compteur eau introuvable : " + idDevice);
        return Response.ok(dto).build();
    }

    @GET
    @Path("/realtime/alerts")
    public Response getDevicesWithAlerts() {
        return Response.ok(waterService.getDevicesWithAlerts()).build();
    }

    @GET
    @Path("/realtime/leaks")
    public Response getDevicesWithLeak() {
        return Response.ok(waterService.getDevicesWithLeak()).build();
    }

    // ═══════════════════════════════════════════════════════════════════════════
    // BRUT (archive_wm)
    // ═══════════════════════════════════════════════════════════════════════════

    /**
     * GET /api/water/raw?device=6101&from=2025-09-01T00:00:00&to=2025-09-02T00:00:00
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
            return Response.ok(waterService.getRawByDeviceAndPeriod(idDevice, range.from, range.to)).build();
        }
        return Response.ok(waterService.getAllRawByPeriod(range.from, range.to)).build();
    }

    @GET
    @Path("/raw/{idDevice}/latest")
    public Response getLatestRaw(@PathParam("idDevice") Integer idDevice) {
        var dto = waterService.getLatestRaw(idDevice);
        if (dto == null) return notFound("Aucune donnée brute pour ce device.");
        return Response.ok(dto).build();
    }

    // ═══════════════════════════════════════════════════════════════════════════
    // HORAIRE (archive_wm_h)
    // ═══════════════════════════════════════════════════════════════════════════

    /**
     * GET /api/water/hourly?device=6101&from=2025-09-01T00:00:00&to=2025-09-07T00:00:00
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
            return Response.ok(waterService.getHourlyByDeviceAndPeriod(idDevice, range.from, range.to)).build();
        }
        return Response.ok(waterService.getAllHourlyByPeriod(range.from, range.to)).build();
    }

    // ═══════════════════════════════════════════════════════════════════════════
    // JOURNALIER (archive_wm_j)
    // ═══════════════════════════════════════════════════════════════════════════

    /**
     * GET /api/water/daily?device=6101&from=2025-09-01T00:00:00&to=2025-09-30T00:00:00
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
            return Response.ok(waterService.getDailyByDeviceAndPeriod(idDevice, range.from, range.to)).build();
        }
        return Response.ok(waterService.getAllDailyByPeriod(range.from, range.to)).build();
    }

    // ═══════════════════════════════════════════════════════════════════════════
    // MENSUEL (archive_wm_m)
    // ═══════════════════════════════════════════════════════════════════════════

    @GET
    @Path("/monthly/{idDevice}")
    public Response getMonthlyByDevice(@PathParam("idDevice") Integer idDevice) {
        return Response.ok(waterService.getMonthlyByDevice(idDevice)).build();
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
            return Response.ok(waterService.getMonthlyByDeviceAndPeriod(idDevice, range.from, range.to)).build();
        }
        return Response.ok(waterService.getAllMonthlyByPeriod(range.from, range.to)).build();
    }

    // ═══════════════════════════════════════════════════════════════════════════
    // RÉSUMÉ / DASHBOARD
    // ═══════════════════════════════════════════════════════════════════════════

    /**
     * GET /api/water/summary/6101?from=2025-09-01T00:00:00&to=2026-01-31T00:00:00
     */
    @GET
    @Path("/summary/{idDevice}")
    public Response getSummary(
            @PathParam("idDevice") Integer idDevice,
            @QueryParam("from")    String  fromStr,
            @QueryParam("to")      String  toStr) {

        DateRange range = parseDateRange(fromStr, toStr, 24 * 30);
        if (range == null) return badRequest("Paramètres from/to invalides.");
        return Response.ok(waterService.getSummary(idDevice, range.from, range.to)).build();
    }

    @GET
    @Path("/summary")
    public Response getAllSummaries(
            @QueryParam("from") String fromStr,
            @QueryParam("to")   String toStr) {

        DateRange range = parseDateRange(fromStr, toStr, 24 * 30);
        if (range == null) return badRequest("Paramètres from/to invalides.");
        return Response.ok(waterService.getAllSummaries(range.from, range.to)).build();
    }

    // ═══════════════════════════════════════════════════════════════════════════
    // CHART DATA
    // ═══════════════════════════════════════════════════════════════════════════

    /**
     * GET /api/water/chart/hourly/6101?from=2025-09-01T00:00:00&to=2025-09-02T00:00:00
     */
    @GET
    @Path("/chart/hourly/{idDevice}")
    public Response getHourlyChart(
            @PathParam("idDevice") Integer idDevice,
            @QueryParam("from")    String  fromStr,
            @QueryParam("to")      String  toStr) {

        DateRange range = parseDateRange(fromStr, toStr, 24);
        if (range == null) return badRequest("Paramètres from/to invalides.");
        return Response.ok(waterService.getHourlyChart(idDevice, range.from, range.to)).build();
    }

    /**
     * GET /api/water/chart/daily/6101?from=2025-09-01T00:00:00&to=2025-09-30T00:00:00
     */
    @GET
    @Path("/chart/daily/{idDevice}")
    public Response getDailyChart(
            @PathParam("idDevice") Integer idDevice,
            @QueryParam("from")    String  fromStr,
            @QueryParam("to")      String  toStr) {

        DateRange range = parseDateRange(fromStr, toStr, 24 * 30);
        if (range == null) return badRequest("Paramètres from/to invalides.");
        return Response.ok(waterService.getDailyChart(idDevice, range.from, range.to)).build();
    }

    /**
     * GET /api/water/chart/monthly/6101?from=2025-09-01T00:00:00&to=2026-01-31T00:00:00
     */
    @GET
    @Path("/chart/monthly/{idDevice}")
    public Response getMonthlyChart(
            @PathParam("idDevice") Integer idDevice,
            @QueryParam("from")    String  fromStr,
            @QueryParam("to")      String  toStr) {

        DateRange range = parseDateRange(fromStr, toStr, 24 * 365);
        if (range == null) return badRequest("Paramètres from/to invalides.");
        return Response.ok(waterService.getMonthlyChart(idDevice, range.from, range.to)).build();
    }

    // ═══════════════════════════════════════════════════════════════════════════
    // STATISTIQUES AVANCÉES
    // ═══════════════════════════════════════════════════════════════════════════

    /**
     * GET /api/water/stats/6101?from=2025-09-01T00:00:00&to=2026-01-31T00:00:00
     */
    @GET
    @Path("/stats/{idDevice}")
    public Response getStats(
            @PathParam("idDevice") Integer idDevice,
            @QueryParam("from")    String  fromStr,
            @QueryParam("to")      String  toStr) {

        DateRange range = parseDateRange(fromStr, toStr, 24 * 30);
        if (range == null) return badRequest("Paramètres from/to invalides.");
        return Response.ok(waterService.getStats(idDevice, range.from, range.to)).build();
    }

    @GET
    @Path("/stats")
    public Response getAllStats(
            @QueryParam("from") String fromStr,
            @QueryParam("to")   String toStr) {

        DateRange range = parseDateRange(fromStr, toStr, 24 * 30);
        if (range == null) return badRequest("Paramètres from/to invalides.");
        return Response.ok(waterService.getAllStats(range.from, range.to)).build();
    }

    // ═══════════════════════════════════════════════════════════════════════════
    // ALERTES
    // ═══════════════════════════════════════════════════════════════════════════

    /** GET /api/water/alerts */
    @GET
    @Path("/alerts")
    public Response getAlerts() {
        return Response.ok(waterService.getActiveAlerts()).build();
    }

    // ═══════════════════════════════════════════════════════════════════════════
    // COMPARAISON
    // ═══════════════════════════════════════════════════════════════════════════

    /**
     * GET /api/water/compare/6101?from=2025-12-01T00:00:00&to=2025-12-31T00:00:00
     */
    @GET
    @Path("/compare/{idDevice}")
    public Response compare(
            @PathParam("idDevice") Integer idDevice,
            @QueryParam("from")    String  fromStr,
            @QueryParam("to")      String  toStr) {

        DateRange range = parseDateRange(fromStr, toStr, 24 * 30);
        if (range == null) return badRequest("Paramètres from/to invalides.");
        return Response.ok(waterService.compareWithPreviousPeriod(idDevice, range.from, range.to)).build();
    }

    // ═══════════════════════════════════════════════════════════════════════════
    // CONFIG (init_wm)
    // ═══════════════════════════════════════════════════════════════════════════

    /** GET /api/water/config/6101 */
    @GET
    @Path("/config/{idDevice}")
    public Response getConfig(@PathParam("idDevice") Integer idDevice) {
        var dto = waterService.getConfig(idDevice);
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
