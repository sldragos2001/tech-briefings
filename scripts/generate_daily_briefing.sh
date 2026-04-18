#!/usr/bin/env bash
set -euo pipefail

SCRIPT_NAME="$(basename "$0")"
LOG_FILE="/tmp/${SCRIPT_NAME%.sh}.log"
DRY_RUN="false"

usage() {
  cat <<'EOF'
Usage:
  generate_daily_briefing.sh [--dry-run]

Description:
  Generates a daily tech briefing in Markdown under:
    briefings/YYYY/MM/YYYY-MM-DD.md

Required environment variables:
  OPENAI_API_KEY
  OPENAI_MODEL         (example: gpt-5.4)
  BRIEFING_LANGUAGE    (example: en)
  OUTPUT_ROOT          (example: briefings)
  TZ                   (example: Europe/Bucharest)

Options:
  --dry-run            Generate output locally without writing final file
  -h, --help           Show this help message
EOF
}

log() {
  printf '%s %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*" | tee -a "$LOG_FILE"
}

cleanup() {
  if [ -n "${TMP_DIR:-}" ] && [ -d "${TMP_DIR}" ]; then
    rm -rf "$TMP_DIR"
  fi
}
trap cleanup EXIT

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || {
    log "ERROR: Required command not found: $1"
    exit 1
  }
}

validate_env() {
  : "${OPENAI_API_KEY:?OPENAI_API_KEY is required}"
  : "${OPENAI_MODEL:?OPENAI_MODEL is required}"
  : "${BRIEFING_LANGUAGE:?BRIEFING_LANGUAGE is required}"
  : "${OUTPUT_ROOT:?OUTPUT_ROOT is required}"
  : "${TZ:?TZ is required}"
}

parse_args() {
  while [ "$#" -gt 0 ]; do
    case "$1" in
      --dry-run)
        DRY_RUN="true"
        shift
        ;;
      -h|--help)
        usage
        exit 0
        ;;
      *)
        log "ERROR: Unknown argument: $1"
        usage
        exit 1
        ;;
    esac
  done
}

main() {
  parse_args "$@"

  require_cmd curl
  require_cmd jq
  require_cmd date
  require_cmd mkdir
  require_cmd tee

  validate_env

  TMP_DIR="$(mktemp -d)"
  PROMPT_FILE="${TMP_DIR}/prompt.txt"
  REQUEST_FILE="${TMP_DIR}/request.json"
  RESPONSE_FILE="${TMP_DIR}/response.json"
  CONTENT_FILE="${TMP_DIR}/briefing.md"

  briefing_date="$(TZ="$TZ" date +%F)"
  year="$(TZ="$TZ" date +%Y)"
  month="$(TZ="$TZ" date +%m)"
  output_dir="${OUTPUT_ROOT}/${year}/${month}"
  output_file="${output_dir}/${briefing_date}.md"

  mkdir -p "$output_dir"

  cat > "$PROMPT_FILE" <<EOF
You are a concise research assistant writing a daily briefing for senior engineering readers.

Task:
Find the top 2 developments of the day in:
1. AI
2. Cloud Computing
3. DevOps

Requirements:
- Write in ${BRIEFING_LANGUAGE}
- Format as a quick briefing readable in under 5 minutes
- Keep it entertaining and easy to digest
- For each development:
  - give a short title
  - summarize it in exactly 3 sentences
  - include a playful "kink" line
  - explain why it matters in 2-3 bullets
- End with a short TL;DR
- Use Markdown
- Today's date in timezone ${TZ} is ${briefing_date}
- Focus on developments of the day or the most recent credible developments available today
- Avoid filler and hype
- Do not include raw URLs
- Target length: 450-650 words
- Do not exceed 700 words
- Keep sentences concise
- Avoid repetition
EOF

  jq -n \
    --rawfile prompt "$PROMPT_FILE" \
    --arg model "$OPENAI_MODEL" \
    '{
      model: $model,
      input: [
        {
          role: "user",
          content: [
            { type: "input_text", text: $prompt }
          ]
        }
      ]
    }' > "$REQUEST_FILE"

  log "Generating daily briefing for ${briefing_date} using model ${OPENAI_MODEL}"

  curl --silent --show-error --fail \
    --request POST \
    --url "https://api.openai.com/v1/responses" \
    --header "Authorization: Bearer ${OPENAI_API_KEY}" \
    --header "Content-Type: application/json" \
    --data @"$REQUEST_FILE" \
    > "$RESPONSE_FILE"

  jq -r '
    if .output_text then
      .output_text
    else
      [
        .output[]?
        | .content[]?
        | select(.type == "output_text")
        | .text
      ] | join("\n")
    end
  ' "$RESPONSE_FILE" > "$CONTENT_FILE"

  if [ ! -s "$CONTENT_FILE" ]; then
    log "ERROR: Generated content is empty"
    log "Response payload:"
    cat "$RESPONSE_FILE" >> "$LOG_FILE"
    exit 1
  fi

  {
    printf '# Daily Tech Briefing — %s\n\n' "$briefing_date"
    cat "$CONTENT_FILE"
    printf '\n'
  } > "${output_file}.tmp"

  if [ "$DRY_RUN" = "true" ]; then
    log "DRY-RUN enabled. Generated file preview:"
    cat "${output_file}.tmp"
    exit 0
  fi

  mv "${output_file}.tmp" "$output_file"
  log "Briefing written to ${output_file}"
}

main "$@"
