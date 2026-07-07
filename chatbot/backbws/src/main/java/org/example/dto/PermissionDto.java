package org.example.dto;

import org.example.entity.Permission;

public class PermissionDto {
    public Integer id;
    public String permission;

    public PermissionDto() {}

    public PermissionDto(Permission p) {
        this.id = p.id;
        this.permission = p.permission;
    }
}
