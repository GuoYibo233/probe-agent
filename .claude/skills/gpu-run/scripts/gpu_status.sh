#!/bin/bash
# Sweep tokyo105-108, print per-GPU: host, index, model, mem used/total, util, owners.
# A GPU is FREE only if it has no compute process from ANY user.
# Usage: gpu_status.sh [host ...]   (default: tokyo105 tokyo106 tokyo107 tokyo108)

HOSTS=("${@:-tokyo105 tokyo106 tokyo107 tokyo108}")
[ $# -eq 0 ] && HOSTS=(tokyo105 tokyo106 tokyo107 tokyo108)

REMOTE_SNIPPET='
declare -A OWNERS
while IFS=, read -r uuid pid mem; do
  uuid=$(echo $uuid | xargs); pid=$(echo $pid | xargs)
  owner=$(ps -o user= -p $pid 2>/dev/null | xargs)
  OWNERS[$uuid]="${OWNERS[$uuid]:+${OWNERS[$uuid]},}${owner:-?}"
done < <(nvidia-smi --query-compute-apps=gpu_uuid,pid,used_memory --format=csv,noheader)
while IFS=, read -r idx uuid name used total util; do
  uuid=$(echo $uuid | xargs)
  o="${OWNERS[$uuid]:-FREE}"
  printf "%s|%s|%s|%s|%s|%s\n" "$(echo $idx|xargs)" "$(echo $name|xargs)" "$(echo $used|xargs)" "$(echo $total|xargs)" "$(echo $util|xargs)" "$o"
done < <(nvidia-smi --query-gpu=index,gpu_uuid,name,memory.used,memory.total,utilization.gpu --format=csv,noheader)
'

SELF=$(hostname)
printf "%-9s %-3s %-28s %-22s %-6s %s\n" HOST GPU MODEL "MEM(used/total)" UTIL OWNERS
for h in "${HOSTS[@]}"; do
  if [ "$h" = "$SELF" ]; then
    out=$(bash -c "$REMOTE_SNIPPET" 2>/dev/null)
  else
    out=$(timeout 15 ssh -o BatchMode=yes -o ConnectTimeout=5 "$h" "$REMOTE_SNIPPET" 2>/dev/null)
  fi
  if [ -z "$out" ]; then
    printf "%-9s %s\n" "$h" "UNREACHABLE"
    continue
  fi
  while IFS='|' read -r idx name used total util owners; do
    printf "%-9s %-3s %-28s %-22s %-6s %s\n" "$h" "$idx" "$name" "$used/$total" "$util" "$owners"
  done <<< "$out"
done
