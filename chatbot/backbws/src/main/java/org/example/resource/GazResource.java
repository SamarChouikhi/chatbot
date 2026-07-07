package org.example.resource;


import jakarta.inject.Inject;
import jakarta.ws.rs.*;
import jakarta.ws.rs.core.MediaType;
import jakarta.ws.rs.core.Response;
import org.example.dto.GazDto.*;
import org.example.service.GazService;

import java.time.LocalDateTime;
import java.time.format.DateTimeParseException;
import java.util.List;

/**
 * REST Resource — Module Gaz
 *
 * Base URL : /api/gaz
 *
 * ┌─────────────────────────────────────────────────────────────────────┐
 * │ GET /api/gaz/realtime               → tous les devices (RT)         │
 * │ GET /api/gaz/realtime/{id}          → un device (RT)                │
 * │ GET /api/gaz/realtime/alerts        → devices en alerte             │
 * │ GET /api/gaz/realtime/leaks         → devices avec fuite            │
 * │                                                                     │
 * │ GET /api/gaz/raw?device=&from=&to=  → données brutes 10min         │
 * │ GET /api/gaz/raw/{id}/latest        → dernière mesure brute         │
 * │                                                                     │
 * │ GET /api/gaz/hourly?device=&from=&to=   → agrégats horaires        │
 * │ GET /api/gaz/daily?device=&from=&to=    → agrégats journaliers      │
 * │ GET /api/gaz/monthly?device=&from=&to=  → agrégats mensuels         │
 * │                                                                     │
 * │ GET /api/gaz/summary/{id}?from=&to= → résumé + CO2 + coût         │
 * │ GET /api/gaz/summary?from=&to=      → résumé tous devices          │
 * │                                                                     │
 * │ GET /api/gaz/chart/daily/{id}?from=&to=   → chart journalier       │
 * │ GET /api/gaz/chart/monthly/{id}?from=&to= → chart mensuel          │
 * │                                                                     │
 * │ GET /api/gaz/alerts                 → toutes alertes actives        │
 * │ GET /api/gaz/compare/{id}?from=&to= → comparaison période préc.    │
 * │                                                                     │
 * │ GET /api/gaz/config/{id}            → config init_gm d'un device   │
 * └─────────────────────────────────────────────────────────────────────┘
 */
@Path("/api/gaz")
@Produces(MediaType.APPLICATION_JSON)
@Consumes(MediaType.APPLICATION_JSON)
public class GazResource {

    @Inject
    GazService gazService;

    // ═══════════════════════════════════════════════════════════════════════════
    // TEMPS RÉEL
    // ═══════════════════════════════════════════════════════════════════════════

    @GET
    @Path("/realtime")
    public Response getAllRealTime() {
        List<RtGmDto> list = gazService.getAllRealTime();
        return Response.ok(list).build();
    }

    @GET
    @Path("/realtime/{idDevice}")
    public Response getRealTime(@PathParam("idDevice") Integer idDevice) {
        RtGmDto dto = gazService.getRealTime(idDevice);
        if (dto == null) return notFound("Compteur gaz introuvable : " + idDevice);
        return Response.ok(dto).build();
    }

    @GET
    @Path("/realtime/alerts")
    public Response getDevicesWithAlerts() {
        return Response.ok(gazService.getDevicesWithAlerts()).build();
    }

    @GET
    @Path("/realtime/leaks")
    public Response getDevicesWithLeak() {
        return Response.ok(gazService.getDevicesWithLeak()).build();
    }

    // ═══════════════════════════════════════════════════════════════════════════
    // BRUT 10 MIN (archive_gm)
    // ═══════════════════════════════════════════════════════════════════════════

    /**
     * GET /api/gaz/raw?device=6201&from=2025-09-01T00:00:00&to=2025-09-02T00:00:00
     * Si device absent → tous les devices
     */
    @GET
    @Path("/raw")
    public Response getRaw(
            @QueryParam("device") Integer idDevice,
            @QueryParam("from")   String  fromStr,
            @QueryParam("to")     String  toStr) {

        DateRange range = parseDateRange(fromStr, toStr, 1); // défaut : dernière heure
        if (range == null) return badRequest("Paramètres from/to invalides.");

        if (idDevice != null) {
            return Response.ok(gazService.getRawByDeviceAndPeriod(idDevice, range.from, range.to)).build();
        }
        return Response.ok(gazService.getAllRawByPeriod(range.from, range.to)).build();
    }

    @GET
    @Path("/raw/{idDevice}/latest")
    public Response getLatestRaw(@PathParam("idDevice") Integer idDevice) {
        var dto = gazService.getLatestRaw(idDevice);
        if (dto == null) return notFound("Aucune donnée brute pour ce device.");
        return Response.ok(dto).build();
    }

    // ═══════════════════════════════════════════════════════════════════════════
    // HORAIRE (archive_gm_h)
    // ═══════════════════════════════════════════════════════════════════════════

    /**
     * GET /api/gaz/hourly?device=6201&from=2025-09-01T00:00:00&to=2025-09-07T00:00:00
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
            return Response.ok(gazService.getHourlyByDeviceAndPeriod(idDevice, range.from, range.to)).build();
        }
        return Response.ok(gazService.getAllHourlyByPeriod(range.from, range.to)).build();
    }

    // ═══════════════════════════════════════════════════════════════════════════
    // JOURNALIER (archive_gm_j)
    // ═══════════════════════════════════════════════════════════════════════════

    /**
     * GET /api/gaz/daily?device=6201&from=2025-09-01T00:00:00&to=2025-09-30T00:00:00
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
            return Response.ok(gazService.getDailyByDeviceAndPeriod(idDevice, range.from, range.to)).build();
        }
        return Response.ok(gazService.getAllDailyByPeriod(range.from, range.to)).build();
    }

    // ═══════════════════════════════════════════════════════════════════════════
    // MENSUEL (archive_gm_m)
    // ═══════════════════════════════════════════════════════════════════════════

    /**
     * GET /api/gaz/monthly/{idDevice}             → tout l'historique mensuel
     * GET /api/gaz/monthly?device=&from=&to=      → filtré par période
     */
    @GET
    @Path("/monthly/{idDevice}")
    public Response getMonthlyByDevice(@PathParam("idDevice") Integer idDevice) {
        return Response.ok(gazService.getMonthlyByDevice(idDevice)).build();
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
            return Response.ok(gazService.getMonthlyByDeviceAndPeriod(idDevice, range.from, range.to)).build();
        }
        return Response.ok(gazService.getAllMonthlyByPeriod(range.from, range.to)).build();
    }

    // ═══════════════════════════════════════════════════════════════════════════
    // RÉSUMÉ / DASHBOARD
    // ═══════════════════════════════════════════════════════════════════════════

    /**
     * GET /api/gaz/summary/6201?from=2025-09-01T00:00:00&to=2026-01-31T00:00:00
     */
    @GET
    @Path("/summary/{idDevice}")
    public Response getSummary(
            @PathParam("idDevice") Integer idDevice,
            @QueryParam("from")    String  fromStr,
            @QueryParam("to")      String  toStr) {

        DateRange range = parseDateRange(fromStr, toStr, 24 * 30);
        if (range == null) return badRequest("Paramètres from/to invalides.");
        return Response.ok(gazService.getSummary(idDevice, range.from, range.to)).build();
    }

    /**
     * GET /api/gaz/summary?from=2025-09-01T00:00:00&to=2026-01-31T00:00:00
     */
    @GET
    @Path("/summary")
    public Response getAllSummaries(
            @QueryParam("from") String fromStr,
            @QueryParam("to")   String toStr) {

        DateRange range = parseDateRange(fromStr, toStr, 24 * 30);
        if (range == null) return badRequest("Paramètres from/to invalides.");
        return Response.ok(gazService.getAllSummaries(range.from, range.to)).build();
    }

    // ═══════════════════════════════════════════════════════════════════════════
    // CHART DATA
    // ═══════════════════════════════════════════════════════════════════════════

    /**
     * GET /api/gaz/chart/daily/6201?from=2025-09-01T00:00:00&to=2025-09-30T00:00:00
     */
    @GET
    @Path("/chart/daily/{idDevice}")
    public Response getDailyChart(
            @PathParam("idDevice") Integer idDevice,
            @QueryParam("from")    String  fromStr,
            @QueryParam("to")      String  toStr) {

        DateRange range = parseDateRange(fromStr, toStr, 24 * 30);
        if (range == null) return badRequest("Paramètres from/to invalides.");
        return Response.ok(gazService.getDailyChart(idDevice, range.from, range.to)).build();
    }

    /**
     * GET /api/gaz/chart/monthly/6201?from=2025-09-01T00:00:00&to=2026-01-31T00:00:00
     */
    @GET
    @Path("/chart/monthly/{idDevice}")
    public Response getMonthlyChart(
            @PathParam("idDevice") Integer idDevice,
            @QueryParam("from")    String  fromStr,
            @QueryParam("to")      String  toStr) {

        DateRange range = parseDateRange(fromStr, toStr, 24 * 365);
        if (range == null) return badRequest("Paramètres from/to invalides.");
        return Response.ok(gazService.getMonthlyChart(idDevice, range.from, range.to)).build();
    }

    // ═══════════════════════════════════════════════════════════════════════════
    // ALERTES
    // ═══════════════════════════════════════════════════════════════════════════

    /** GET /api/gaz/alerts */
    @GET
    @Path("/alerts")
    public Response getAlerts() {
        return Response.ok(gazService.getActiveAlerts()).build();
    }

    // ═══════════════════════════════════════════════════════════════════════════
    // COMPARAISON
    // ═══════════════════════════════════════════════════════════════════════════

    /**
     * GET /api/gaz/compare/6201?from=2025-12-01T00:00:00&to=2025-12-31T00:00:00
     * Compare la période sélectionnée avec la période précédente de même durée.
     */
    @GET
    @Path("/compare/{idDevice}")
    public Response compare(
            @PathParam("idDevice") Integer idDevice,
            @QueryParam("from")    String  fromStr,
            @QueryParam("to")      String  toStr) {

        DateRange range = parseDateRange(fromStr, toStr, 24 * 30);
        if (range == null) return badRequest("Paramètres from/to invalides.");
        return Response.ok(gazService.compareWithPreviousPeriod(idDevice, range.from, range.to)).build();
    }

    // ═══════════════════════════════════════════════════════════════════════════
    // CONFIG (init_gm)
    // ═══════════════════════════════════════════════════════════════════════════

    /** GET /api/gaz/config/6201 */
    @GET
    @Path("/config/{idDevice}")
    public Response getConfig(@PathParam("idDevice") Integer idDevice) {
        var dto = gazService.getConfig(idDevice);
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

    /**
     * Parse les query params from/to.
     * Si absent, calcule une plage par défaut (now - defaultHours → now).
     */
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
