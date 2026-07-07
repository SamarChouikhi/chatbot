package org.example.resource;

import jakarta.enterprise.context.ApplicationScoped;
import jakarta.inject.Inject;
import jakarta.ws.rs.*;
import org.jboss.logging.Logger;
import jakarta.ws.rs.core.MediaType;
import jakarta.ws.rs.core.Response;
import org.example.dto.KpiDto;
import org.example.service.KpiService;

@Path("/api/kpis")
@Produces(MediaType.APPLICATION_JSON)
@Consumes(MediaType.APPLICATION_JSON)
@ApplicationScoped
public class KpiResource {

    private static final Logger LOG = Logger.getLogger(KpiResource.class);

    @Inject
    KpiService kpiService;

    @GET
    @Path("/summary")
    public Response getSummary() {
        try {
            return Response.ok(kpiService.getSummary()).build();
        } catch (Exception e) {
            return error(e);
        }
    }

    @GET
    @Path("/chart-data")
    public Response getChartData(@QueryParam("period") @DefaultValue("30") int days) {
        try {
            int safe = Math.max(1, Math.min(days, 365));
            KpiDto dto    = new KpiDto();
            dto.chartData = kpiService.getChartData(safe);
            return Response.ok(dto).build();
        } catch (Exception e) {
            return error(e);
        }
    }

    @GET
    @Path("/device-stats")
    public Response getDeviceStats() {
        try {
            return Response.ok(kpiService.getDeviceStats()).build();
        } catch (Exception e) {
            return error(e);
        }
    }

    @GET
    @Path("/alerts")
    public Response getAlerts(@QueryParam("limit") @DefaultValue("10") int limit) {
        try {
            KpiDto dto = new KpiDto();
            dto.alerts = kpiService.getRecentAlerts(limit);
            return Response.ok(dto).build();
        } catch (Exception e) {
            return error(e);
        }
    }

    @GET
    @Path("/full")
    public Response getFullDashboard() {
        try {
            return Response.ok(kpiService.getFullDashboard()).build();
        } catch (Exception e) {
            return error(e);
        }
    }

    private Response error(Exception e) {
        LOG.error("Erreur KPI", e);
        return Response.serverError()
            .entity("{\"error\":\"Erreur interne du serveur\"}")
            .build();
    }
}
