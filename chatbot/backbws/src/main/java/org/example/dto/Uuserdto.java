package org.example.dto;

import org.example.entity.UUser;
import java.time.LocalDate;
import java.time.LocalDateTime;

public class Uuserdto {

    public String        login;
    public String        pwd;
    public String        loginPere;
    public LocalDate     pwdExpDate;
    public Integer       gmtPlus;
    public Integer       isAdvisor;
    public String        loginFb;
    public String        idFb;
    public String        idFbMsg;
    public String        resetToken;
    public LocalDateTime resetTokenExpiry;
    public String        phone;
    public Integer       failedAttempts;
    public LocalDateTime blockedUntil;
    public Integer       roleId;
    public String        roleName;

    public Uuserdto() {}

    public Uuserdto(UUser u) {
        this.login            = u.login;
        this.pwd              = null;
        this.loginPere        = u.loginPere;
        this.pwdExpDate       = u.pwdExpDate;
        this.gmtPlus          = u.gmtPlus;
        this.isAdvisor        = u.isAdvisor;
        this.loginFb          = u.loginFb;
        this.idFb             = u.idFb;
        this.idFbMsg          = u.idFbMsg;
        this.resetToken       = u.resetToken;
        this.resetTokenExpiry = u.resetTokenExpiry;
        this.phone            = u.phone;
        this.failedAttempts   = u.failedAttempts;
        this.blockedUntil     = u.blockedUntil;
        this.roleId           = u.userRole != null ? u.userRole.id       : null;
        this.roleName         = u.userRole != null ? u.userRole.userName : null;
    }
}