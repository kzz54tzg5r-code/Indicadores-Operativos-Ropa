"""Autorización por rol y alcance. La restricción se aplica a los datos, no solo a la interfaz."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Iterable
import pandas as pd
ROLE_LEVEL={"CONSULTA":10,"SUPERVISOR":20,"TIENDA":30,"REGIONAL":40,"DIRECTOR":50,"ADMIN":80,"OWNER":100}
@dataclass(frozen=True)
class AccessContext:
    role: str
    scope: str="COMPANY"
    regions: tuple[str,...]=field(default_factory=tuple)
    stores: tuple[str,...]=field(default_factory=tuple)
    team: tuple[str,...]=field(default_factory=tuple)
    activities: tuple[str,...]=field(default_factory=tuple)
    user_id: str=""
    def normalized_role(self): return str(self.role or "CONSULTA").upper()

def can(ctx: AccessContext, action: str) -> bool:
    role=ctx.normalized_role(); level=ROLE_LEVEL.get(role,0)
    action=action.lower()
    if action in {"system_control","restore_backup","owner_admin"}: return role=="OWNER"
    if action in {"manage_users","upload","goals","diagnostics"}: return level>=ROLE_LEVEL["ADMIN"]
    if action in {"export","read"}: return level>=ROLE_LEVEL["CONSULTA"]
    return False

def protect_owner(actor: AccessContext, target_role: str, operation: str) -> None:
    if str(target_role).upper()=="OWNER" and actor.normalized_role()!="OWNER":
        raise PermissionError("El OWNER solo puede ser administrado por otro OWNER autorizado.")
    if str(target_role).upper()=="OWNER" and operation.lower() in {"delete","degrade"}:
        raise PermissionError("El OWNER no puede eliminarse ni degradarse.")

def apply_scope(df: pd.DataFrame, ctx: AccessContext, *, store_col="Tienda", region_col="Región", employee_col="Nombre", activity_col="Actividad") -> pd.DataFrame:
    if df is None or df.empty: return pd.DataFrame() if df is None else df.copy()
    out=df.copy(); scope=str(ctx.scope or "COMPANY").upper(); role=ctx.normalized_role()
    if role in {"OWNER","ADMIN","DIRECTOR"} and scope=="COMPANY": return out
    if scope=="REGION":
        if region_col not in out.columns: return out.iloc[0:0].copy()
        out=out[out[region_col].astype(str).isin(ctx.regions)]
    elif scope in {"STORE","TEAM"}:
        if store_col not in out.columns: return out.iloc[0:0].copy()
        out=out[out[store_col].astype(str).isin(ctx.stores)]
    if scope=="TEAM" and ctx.team:
        if employee_col not in out.columns: return out.iloc[0:0].copy()
        out=out[out[employee_col].astype(str).isin(ctx.team)]
    if role=="SUPERVISOR" and ctx.activities:
        if activity_col not in out.columns: return out.iloc[0:0].copy()
        out=out[out[activity_col].astype(str).isin(ctx.activities)]
    return out.copy()
