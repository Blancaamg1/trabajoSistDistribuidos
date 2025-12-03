#!/bin/bash

tmux -f .tmux.conf new-session -d -s session
tmux -f .tmux.conf split-window -h
tmux -f .tmux.conf split-window -v
tmux -f .tmux.conf send-keys -t session:0.0 "./media_server.py server.config" C-m
tmux -f .tmux.conf send-keys -t session:0.1 "./media_render.py render.config" C-m
tmux -f .tmux.conf send-keys -t session:0.2 "./media_control.py control.config" C-m
tmux -f .tmux.conf attach-session -t session
