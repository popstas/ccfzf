# ccfzf zsh widget — bind the project/session picker to a key.
#
#   source /path/to/ccfzf/ccfzf.zsh
#
# `ccfzf --print` returns the command instead of running it, so the real
# command lands in the shell history and the shell stays in the project
# directory after claude exits — the same way ctrl-g of fzf-marks leaves you
# in the directory you jumped to.

ccfzf-widget() {
  local cmd
  cmd=$(ccfzf --print) || { zle redisplay; return 0 }   # esc — return quietly
  [[ -z $cmd ]] && { zle redisplay; return 0 }
  [[ -n $BUFFER ]] && zle push-line                     # keep a half-typed line
  BUFFER=$cmd
  zle accept-line
}
zle -N ccfzf-widget
bindkey "${CCFZF_KEY:-^t}" ccfzf-widget
