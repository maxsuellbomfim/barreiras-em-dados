-- Reforça o search_path fixo da função auxiliar de normalização.
alter function api.pncp_label_key(text) set search_path = '';
