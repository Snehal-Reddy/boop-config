#!/bin/bash
# Smoked Glass Rofi Power Menu

lock="  Lock"
reboot="  Reboot"
shutdown="  Shutdown"

chosen=$(printf "%s\n%s\n%s\n" "$lock" "$reboot" "$shutdown" | \
    rofi -dmenu -i -p "Power" -hover-select -me-select-entry '' -me-accept-entry MousePrimary -theme-str '
        window {
            width: 240px;
            border: 1px;
            border-radius: 14px;
            border-color: #363F54;
            background-color: #12141AE8;
            location: northeast;
            anchor: northeast;
            x-offset: -26px;
            y-offset: 44px;
            padding: 10px;
        }
        mainbox {
            background-color: transparent;
            children: [ listview ];
        }
        listview {
            lines: 3;
            columns: 1;
            spacing: 4px;
            background-color: transparent;
            border: 0px;
            scrollbar: false;
        }
        element {
            padding: 8px 12px;
            border-radius: 8px;
            background-color: transparent;
            text-color: #D8DEE9;
        }
        element selected {
            background-color: #363F54;
            text-color: #89B4FA;
        }
        element-text {
            background-color: transparent;
            text-color: inherit;
            font: "Noto Sans 11";
        }
    ')

case "$chosen" in
    "$lock")
        sleep 0.1
        "$HOME/.config/scripts/lock"
        ;;
    "$reboot")
        systemctl reboot
        ;;
    "$shutdown")
        systemctl poweroff
        ;;
esac
