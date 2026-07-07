package org.example.service;

import io.quarkus.scheduler.Scheduled;
import jakarta.enterprise.context.ApplicationScoped;
import jakarta.transaction.Transactional;
import org.example.entity.ArchiveWm;
import org.example.entity.ArchiveWmId;
import org.example.entity.RtWm;
import org.jboss.logging.Logger;

import java.util.List;

/**
 * Archive periodically the current rt_wm snapshot into archive_wm.
 * rt_wm holds ONE row per device (last known state) — without this job
 * archive_wm stays empty and the Python AD pipeline has no water history.
 *
 * forward_flow = delta between current wmIndex and the previous archived index.
 * wmIndex      = cumulative meter reading (liters).
 */
@ApplicationScoped
public class WaterArchiveJob {

    private static final Logger LOG = Logger.getLogger(WaterArchiveJob.class);

    @Scheduled(every = "10m")
    @Transactional
    public void archiveRtWm() {
        List<RtWm> devices = RtWm.findAllActive();
        int inserted = 0;

        for (RtWm rt : devices) {
            if (rt.date == null || rt.wmIndex == null) continue;

            // Idempotent: skip if this exact (device, timestamp) already archived
            boolean exists = ArchiveWm.count(
                    "id.idDevice = ?1 AND id.date = ?2",
                    rt.idDevice, rt.date) > 0;
            if (exists) continue;

            // Delta consumption since last archived reading
            ArchiveWm prev = ArchiveWm
                    .find("id.idDevice = ?1 ORDER BY id.date DESC", rt.idDevice)
                    .firstResult();
            int prevIndex   = (prev != null && prev.wmIndex != null) ? prev.wmIndex : 0;
            int forwardFlow = Math.max(0, rt.wmIndex - prevIndex);   // liters, never negative

            ArchiveWm a = new ArchiveWm();
            a.id           = new ArchiveWmId(rt.idDevice, rt.date);
            a.forwardFlow  = forwardFlow;
            a.reverseFlow  = 0;
            a.tamp         = 0;
            a.wmIndex      = rt.wmIndex;
            a.leak         = rt.leak   != null ? rt.leak   : 0;
            a.fraud        = rt.fraud  != null ? rt.fraud  : 0;
            a.sens         = rt.sens   != null ? rt.sens   : 0;
            a.batteryLevel = rt.batteryLevel != null ? rt.batteryLevel : 255;
            a.ctr          = rt.ctr    != null ? rt.ctr    : 0;
            a.snr          = rt.snr    != null ? rt.snr    : 0;
            a.rssi         = rt.rssi   != null ? rt.rssi   : 0;
            a.gateway      = rt.gateway != null ? rt.gateway : 0;
            a.persist();
            inserted++;
        }

        if (inserted > 0)
            LOG.infof("[WaterArchiveJob] %d snapshot(s) archived to archive_wm", inserted);
    }
}
