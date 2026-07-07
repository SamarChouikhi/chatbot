package org.example.entity;


import io.quarkus.hibernate.orm.panache.PanacheEntityBase;
import jakarta.persistence.*;
import java.time.LocalDateTime;

/**
 * Table init_gm — état et configuration des compteurs gaz
 * Clé primaire : id_device
 */
@Entity
@Table(name = "init_gm")
public class InitGm extends PanacheEntityBase {

    @Id
    @Column(name = "id_device")
    public Integer idDevice;

    @Column(name = "date")
    public LocalDateTime date;

    @Column(name = "forward_flow")
    public Integer forwardFlow = 0;

    @Column(name = "forward_flow_back")
    public Integer forwardFlowBack = 0;

    @Column(name = "reverse_flow")
    public Integer reverseFlow = 0;

    @Column(name = "reverse_flow_back")
    public Integer reverseFlowBack = 0;

    @Column(name = "tamp")
    public Integer tamp = 0;

    @Column(name = "tamp_back")
    public Integer tampBack = 0;

    @Column(name = "uptime")
    public Integer uptime = 0;

    @Column(name = "conso_h")
    public Integer consoH = 0;

    @Column(name = "conso_j")
    public Integer consoJ = 0;

    @Column(name = "conso_m")
    public Integer consoM = 0;

    @Column(name = "reverse_conso_h")
    public Integer reverseConsoH = 0;

    @Column(name = "reverse_conso_j")
    public Integer reverseConsoJ = 0;

    @Column(name = "reverse_conso_m")
    public Integer reverseConsoM = 0;

    @Column(name = "infraction_conso_h")
    public Integer infractionConsoH = 0;

    @Column(name = "infraction_conso_j")
    public Integer infractionConsoJ = 0;

    @Column(name = "infraction_conso_m")
    public Integer infractionConsoM = 0;

    @Column(name = "alert_state")
    public Integer alertState = 0;

    @Column(name = "start_check_alert_date")
    public LocalDateTime startCheckAlertDate;

    @Column(name = "high_consumption_counter")
    public Integer highConsumptionCounter = 0;

    @Column(name = "excessive_consumption_counter")
    public Integer excessiveConsumptionCounter = 0;

    @Column(name = "low_consumption_counter")
    public Integer lowConsumptionCounter = 0;

    @Column(name = "min_debit_per_min")
    public Double minDebitPerMin = 0.0;

    @Column(name = "max_debit_per_min")
    public Double maxDebitPerMin = 0.0;

    @Column(name = "avg_debit_per_min")
    public Double avgDebitPerMin = 0.0;

    @Column(name = "crc")
    public Integer crc = 0;

    @Column(name = "min_debit_per_min_back")
    public Double minDebitPerMinBack = 0.0;

    @Column(name = "max_debit_per_min_back")
    public Double maxDebitPerMinBack = 0.0;

    @Column(name = "avg_debit_per_min_back")
    public Double avgDebitPerMinBack = 0.0;

    @Column(name = "crc_back")
    public Integer crcBack = 0;

    // ── Queries ───────────────────────────────────────────────────────────

    public static InitGm findByDevice(Integer idDevice) {
        return findById(idDevice);
    }
}

