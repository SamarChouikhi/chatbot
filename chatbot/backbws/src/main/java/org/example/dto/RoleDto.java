package org.example.dto;

import org.example.entity.UserRole;
import java.util.List;
import java.util.stream.Collectors;

public class RoleDto {
    public Integer id;
    public String userName;
    public List<PermissionDto> permissions;

    public RoleDto() {}

    public RoleDto(UserRole r) {
        this.id = r.id;
        this.userName = r.userName;
        this.permissions = r.permissions == null ? List.of() :
            r.permissions.stream()
                .map(PermissionDto::new)
                .collect(Collectors.toList());
    }
}
