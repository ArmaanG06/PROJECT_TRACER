import math 

def levels(signal_cfg, costs_over_sigma):
    entry_z = signal_cfg["entry_z"]
    exit_z = signal_cfg["exit_z"]
    stop_z = signal_cfg["stop_z"]
    threshold_mode = signal_cfg["threshold_mode"]
    cost_aware_mult = signal_cfg["cost_aware_mult"]

    if threshold_mode == "fixed":
        return entry_z, exit_z, stop_z 

    if threshold_mode == "cost_aware":
        entry_level = max(entry_z, cost_aware_mult * costs_over_sigma)
        stop_level = entry_level + (stop_z - entry_z)
        exit_level = exit_z
        return entry_level, exit_level, stop_level

    raise ValueError(f"unknown threshold_mode: {threshold_mode!r} (use fixed | cost_aware)")

def next_action(z_today, direction, days_held, entry_half_life, broken, can_enter, entry_level, exit_level, stop_level, signal_cfg, breakdown_cfg):
    
    if direction  == +1 or direction == -1:
        if broken and breakdown_cfg["action"] == "force_close":
            return 0, "exit_broken"
        if days_held >= signal_cfg["time_stop_mult"] * entry_half_life:
            return 0, "exit_time"
        if math.isnan(z_today):
            return direction, "hold_no_data"

        if direction == 1 and z_today <= -stop_level:
            return 0, "exit_stop"
        if direction == -1 and z_today >= stop_level:
            return 0 , "exit_stop"

        if direction == 1 and z_today >= -exit_level:
            return 0, "exit_profit"
        if direction == -1 and z_today <= exit_level:
            return 0, "exit_profit"

        return direction, "hold"

    if direction == 0:
        if not can_enter:
            return 0, "flat_exit_only"
        if math.isnan(z_today):
            return 0, "flat_no_data"
        if abs(z_today) >= stop_level:
            return 0, "flat_too_stretched"
        if z_today >= entry_level:
            return -1, "enter_short"
        if z_today <= -entry_level:
            return 1, "enter_long"
        
        return 0, "flat"
     
                