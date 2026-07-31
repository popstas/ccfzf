# ccfzf zsh widgets — bind the project/session picker to a key.
#
#   source /path/to/ccfzf/ccfzf.zsh
#
# Two widgets, because there are two useful behaviours:
#
#   ccfzf-kiosk-widget  runs `ccfzf --kiosk`: everything happens inside ccfzf
#                       and on exit you are back in the session list. Bound to
#                       ctrl-t by default ($CCFZF_KEY).
#   ccfzf-widget        runs `ccfzf --print`, which returns the command instead
#                       of running it: the real command lands in the shell
#                       history and the shell stays in the project directory
#                       afterwards, the way ctrl-g of fzf-marks leaves you in
#                       the directory you jumped to. Bind it to $CCFZF_PRINT_KEY
#                       or swap the bindkey below if you prefer this one.

ccfzf-kiosk-widget() {
  [[ -n $BUFFER ]] && zle push-line          # keep a half-typed line
  BUFFER="ccfzf --kiosk"
  zle accept-line
}
zle -N ccfzf-kiosk-widget

ccfzf-widget() {
  local cmd
  cmd=$(ccfzf --print) || { zle redisplay; return 0 }   # esc — return quietly
  [[ -z $cmd ]] && { zle redisplay; return 0 }
  [[ -n $BUFFER ]] && zle push-line
  BUFFER=$cmd
  zle accept-line
}
zle -N ccfzf-widget

bindkey "${CCFZF_KEY:-^t}" ccfzf-kiosk-widget
[[ -n ${CCFZF_PRINT_KEY:-} ]] && bindkey "$CCFZF_PRINT_KEY" ccfzf-widget
