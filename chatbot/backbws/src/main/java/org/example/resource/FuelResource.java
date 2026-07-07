package org.example.resource;

import jakarta.inject.Inject;
import jakarta.ws.rs.*;
import jakarta.ws.rs.core.MediaType;
import jakarta.ws.rs.core.Response;
import org.example.dto.FuelDto.*;
import org.example.service.FuelService;

import java.time.LocalDateTime;
import java.time.format.DateTimeParseException;
import java.util.List;

/**
 * REST Resource — Module Carburant (Fuel)
 *
 * Base URL : /api/fuel
 *
 * ┌──────────────────────────────────────────────────────────────────────────┐
 * │ GET /api/fuel/latest                    → dernier état tous véhicules    │
 * │ GET /api/fuel/latest/{id}               → dernier état un véhicule       │
 * │                                                                          │
 * │ GET /api/fuel/raw?device=&from=&to=     → données brutes IoT             │
 * │ GET /api/fuel/raw/{id}/latest           → dernière mesure brute          │
 * │                                                                          │
 * │ GET /api/fuel/hourly?device=&from=&to=  → agrégats horaires              │
 * │ GET /api/fuel/daily?device=&from=&to=   → agrégats journaliers           │
 * │ GET /api/fuel/monthly?device=&from=&to= → agrégats mensuels              │
 * │ GET /api/fuel/monthly/{id}              → tout l'historique mensuel      │
 * │                                                                          │
 * │ GET /api/fuel/consumption/{id}          → fuel_consumption par véhicule  │
 * │ GET /api/fuel/consumption?from=&to=     → fuel_consumption sur période   │
 * │                                                                          │
 * │ GET /api/fuel/summary/{id}?from=&to=    → résumé + CO2 + coût           │
 * │ GET /api/fuel/summary?from=&to=         → résumé tous véhicules          │
 * │                                                                          │
 * │ GET /api/fuel/chart/daily/{id}?from=&to=    → chart journalier           │
 * │ GET /api/fuel/chart/monthly/{id}?from=&to=  → chart mensuel              │
 * │                                                                          │
 * │ GET /api/fuel/stats/{id}?from=&to=      → statistiques avancées          │
 * │ GET /api/fuel/stats?from=&to=           → stats tous véhicules           │
 * │                                                                          │
 * │ GET /api/fuel/alerts                    → alertes actives                │
 * │ GET /api/fuel/compare/{id}?from=&to=    → comparaison période préc.      │
 * └──────────────────────────────────────────────────────────────────────────┘
 */
@Path("/api/fuel")
@Produces(MediaType.APPLICATION_JSON)
@Consumes(MediaType.APPLICATION_JSON)
public class FuelResource {

    @Inject
    FuelService fuelService;

    // ═══════════════════════════════════════════════════════════════════════════
    // DERNIER ÉTAT
    // ═══════════════════════════════════════════════════════════════════════════

    @GET
    @Path("/latest")
    public Response getAllLatest() {
        List<FuelLatestDto> list = fuelService.getAllLatest();
        return Response.ok(list).build();
    }

    @GET
    @Path("/latest/{deviceId}")
    public Response getLatest(@PathParam("deviceId") Integer deviceId) {
        FuelLatestDto dto = fuelService.getLatest(deviceId);
        if (dto == null) return notFound("Véhicule introuvable : " + deviceId);
        return Response.ok(dto).build();
    }

    // ═══════════════════════════════════════════════════════════════════════════
    // BRUT (archive_fuel)
    // ═══════════════════════════════════════════════════════════════════════════

    @GET
    @Path("/raw")
    public Response getRaw(
            @QueryParam("device") Integer idDevice,
            @QueryParam("from")   String  fromStr,
            @QueryParam("to")     String  toStr) {

        DateRange range = parseDateRange(fromStr, toStr, 1);
        if (range == null) return badRequest("Paramètres from/to invalides.");
        if (idDevice != null)
            return Response.ok(fuelService.getRawByDeviceAndPeriod(idDevice, range.from, range.to)).build();
        return Response.ok(fuelService.getAllRawByPeriod(range.from, range.to)).build();
    }

    @GET
    @Path("/raw/{idDevice}/latest")
    public Response getLatestRaw(@PathParam("idDevice") Integer idDevice) {
        var dto = fuelService.getLatestRaw(idDevice);
        if (dto == null) return notFound("Aucune donnée brute pour ce véhicule.");
        return Response.ok(dto).build();
    }

    // ═══════════════════════════════════════════════════════════════════════════
    // HORAIRE (archive_fuel_h)
    // ═══════════════════════════════════════════════════════════════════════════

    @GET
    @Path("/hourly")
    public Response getHourly(
            @QueryParam("device") Integer idDevice,
            @QueryParam("from")   String  fromStr,
            @QueryParam("to")     String  toStr) {

        DateRange range = parseDateRange(fromStr, toStr, 24);
        if (range == null) return badRequest("Paramètres from/to invalides.");
        if (idDevice != null)
            return Response.ok(fuelService.getHourlyByDeviceAndPeriod(idDevice, range.from, range.to)).build();
        return Response.ok(fuelService.getAllHourlyByPeriod(range.from, range.to)).build();
    }

    // ═══════════════════════════════════════════════════════════════════════════
    // JOURNALIER (archive_fuel_j)
    // ═══════════════════════════════════════════════════════════════════════════

    @GET
    @Path("/daily")
    public Response getDaily(
            @QueryParam("device") Integer idDevice,
            @QueryParam("from")   String  fromStr,
            @QueryParam("to")     String  toStr) {

        DateRange range = parseDateRange(fromStr, toStr, 24 * 30);
        if (range == null) return badRequest("Paramètres from/to invalides.");
        if (idDevice != null)
            return Response.ok(fuelService.getDailyByDeviceAndPeriod(idDevice, range.from, range.to)).build();
        return Response.ok(fuelService.getAllDailyByPeriod(range.from, range.to)).build();
    }

    // ═══════════════════════════════════════════════════════════════════════════
    // MENSUEL (archive_fuel_m)
    // ═══════════════════════════════════════════════════════════════════════════

    @GET
    @Path("/monthly/{idDevice}")
    public Response getMonthlyByDevice(@PathParam("idDevice") Integer idDevice) {
        return Response.ok(fuelService.getMonthlyByDevice(idDevice)).build();
    }

    @GET
    @Path("/monthly")
    public Response getMonthly(
            @QueryParam("device") Integer idDevice,
            @QueryParam("from")   String  fromStr,
            @QueryParam("to")     String  toStr) {

        DateRange range = parseDateRange(fromStr, toStr, 24 * 365);
        if (range == null) return badRequest("Paramètres from/to invalides.");
        if (idDevice != null)
            return Response.ok(fuelService.getMonthlyByDeviceAndPeriod(idDevice, range.from, range.to)).build();
        return Response.ok(fuelService.getAllMonthlyByPeriod(range.from, range.to)).build();
    }

    // ═══════════════════════════════════════════════════════════════════════════
    // fuel_consumption
    // ═══════════════════════════════════════════════════════════════════════════

    @GET
    @Path("/consumption/{deviceId}")
    public Response getConsumptionByDevice(@PathParam("deviceId") Integer deviceId) {
        return Response.ok(fuelService.getConsumptionByDevice(deviceId)).build();
    }

    @GET
    @Path("/consumption")
    public Response getConsumptionByPeriod(
            @QueryParam("from") String fromStr,
            @QueryParam("to")   String toStr) {

        DateRange range = parseDateRange(fromStr, toStr, 24 * 30);
        if (range == null) return badRequest("Paramètres from/to invalides.");
        return Response.ok(fuelService.getConsumptionByPeriod(range.from, range.to)).build();
    }

    // ═══════════════════════════════════════════════════════════════════════════
    // RÉSUMÉ / DASHBOARD
    // ═══════════════════════════════════════════════════════════════════════════

    @GET
    @Path("/summary/{deviceId}")
    public Response getSummary(
            @PathParam("deviceId") Integer deviceId,
            @QueryParam("from")    String  fromStr,
            @QueryParam("to")      String  toStr) {

        DateRange range = parseDateRange(fromStr, toStr, 24 * 30);
        if (range == null) return badRequest("Paramètres from/to invalides.");
        return Response.ok(fuelService.getSummary(deviceId, range.from, range.to)).build();
    }

    @GET
    @Path("/summary")
    public Response getAllSummaries(
            @QueryParam("from") String fromStr,
            @QueryParam("to")   String toStr) {

        DateRange range = parseDateRange(fromStr, toStr, 24 * 30);
        if (range == null) return badRequest("Paramètres from/to invalides.");
        return Response.ok(fuelService.getAllSummaries(range.from, range.to)).build();
    }

    // ═══════════════════════════════════════════════════════════════════════════
    // CHART DATA
    // ═══════════════════════════════════════════════════════════════════════════

    @GET
    @Path("/chart/daily/{deviceId}")
    public Response getDailyChart(
            @PathParam("deviceId") Integer deviceId,
            @QueryParam("from")    String  fromStr,
            @QueryParam("to")      String  toStr) {

        DateRange range = parseDateRange(fromStr, toStr, 24 * 30);
        if (range == null) return badRequest("Paramètres from/to invalides.");
        return Response.ok(fuelService.getDailyChart(deviceId, range.from, range.to)).build();
    }

    @GET
    @Path("/chart/monthly/{deviceId}")
    public Response getMonthlyChart(
            @PathParam("deviceId") Integer deviceId,
            @QueryParam("from")    String  fromStr,
            @QueryParam("to")      String  toStr) {

        DateRange range = parseDateRange(fromStr, toStr, 24 * 365);
        if (range == null) return badRequest("Paramètres from/to invalides.");
        return Response.ok(fuelService.getMonthlyChart(deviceId, range.from, range.to)).build();
    }

    // ═══════════════════════════════════════════════════════════════════════════
    // STATISTIQUES AVANCÉES
    // ═══════════════════════════════════════════════════════════════════════════

    @GET
    @Path("/stats/{deviceId}")
    public Response getStats(
            @PathParam("deviceId") Integer deviceId,
            @QueryParam("from")    String  fromStr,
            @QueryParam("to")      String  toStr) {

        DateRange range = parseDateRange(fromStr, toStr, 24 * 30);
        if (range == null) return badRequest("Paramètres from/to invalides.");
        return Response.ok(fuelService.getStats(deviceId, range.from, range.to)).build();
    }

    @GET
    @Path("/stats")
    public Response getAllStats(
            @QueryParam("from") String fromStr,
            @QueryParam("to")   String toStr) {

        DateRange range = parseDateRange(fromStr, toStr, 24 * 30);
        if (range == null) return badRequest("Paramètres from/to invalides.");
        return Response.ok(fuelService.getAllStats(range.from, range.to)).build();
    }

    // ═══════════════════════════════════════════════════════════════════════════
    // ALERTES
    // ═══════════════════════════════════════════════════════════════════════════

    @GET
    @Path("/alerts")
    public Response getAlerts() {
        return Response.ok(fuelService.getActiveAlerts()).build();
    }

    // ═══════════════════════════════════════════════════════════════════════════
    // COMPARAISON
    // ═══════════════════════════════════════════════════════════════════════════

    @GET
    @Path("/compare/{deviceId}")
    public Response compare(
            @PathParam("deviceId") Integer deviceId,
            @QueryParam("from")    String  fromStr,
            @QueryParam("to")      String  toStr) {

        DateRange range = parseDateRange(fromStr, toStr, 24 * 30);
        if (range == null) return badRequest("Paramètres from/to invalides.");
        return Response.ok(fuelService.compareWithPreviousPeriod(deviceId, range.from, range.to)).build();
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
