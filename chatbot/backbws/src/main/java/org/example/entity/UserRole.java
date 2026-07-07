package org.example.entity;

import io.quarkus.hibernate.orm.panache.PanacheEntityBase;
import jakarta.persistence.*;
import java.util.HashSet;
import java.util.Set;

@Entity
@Table(name = "user_roles", schema = "bw_samar")
public class UserRole extends PanacheEntityBase {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    public Integer id;

    @Column(name = "userName", length = 50, nullable = false, unique = true)
    public String userName;

    @ManyToMany(fetch = FetchType.EAGER)
    @JoinTable(
        name = "userRole_permission",
        schema = "bw_samar",
        joinColumns = @JoinColumn(name = "userRole_id"),
        inverseJoinColumns = @JoinColumn(name = "permission_id")
    )
    public Set<Permission> permissions = new HashSet<>();

    public static UserRole findByName(String name) {
        return find("userName", name).firstResult();
    }
}
