package org.example.entity;

import io.quarkus.hibernate.orm.panache.PanacheEntityBase;
import jakarta.persistence.*;

@Entity
@Table(name = "u_user_permissions", schema = "bw_samar")
public class Permission extends PanacheEntityBase {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    public Integer id;

    @Column(name = "permission", length = 100, nullable = false, unique = true)
    public String permission;

    public static Permission findByName(String name) {
        return find("permission", name).firstResult();
    }
}
