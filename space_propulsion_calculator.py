import json
import math
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk


G0 = 9.80665
E_CHARGE = 1.602176634e-19
AMU = 1.66053906660e-27
EPS0 = 8.8541878128e-12
MU0 = 4.0 * math.pi * 1e-7
C_LIGHT = 299_792_458.0
ME = 9.1093837015e-31
KB = 1.380649e-23
AU = 149_597_870_700.0
SIGMA_SB = 5.670374419e-8


PROPELLANTS = {
    "Xenon": 131.293,
    "Krypton": 83.798,
    "Argon": 39.948,
    "Iodine": 126.90447,
    "Bismuth": 208.98040,
    "Cesium": 132.90545,
    "Lithium": 6.94,
    "Hydrogen": 1.00784,
    "Nitrogen": 14.0067,
    "Water": 18.01528,
    "Ammonia": 17.03052,
    "PTFE equivalent": 100.0,
}


ELECTRIC_PRESETS = {
    "Blank/custom": {},
    "NSTAR ion, high throttle": {
        "family": "Gridded ion",
        "power_w": 2300,
        "efficiency": 0.61,
        "specific_impulse_s": 3100,
        "thrust_mn": 92,
        "mass_flow_mg_s": 3.03,
        "beam_voltage_v": 1300,
        "propellant": "Xenon",
    },
    "NEXT ion, high throttle": {
        "family": "Gridded ion",
        "power_w": 6900,
        "efficiency": 0.70,
        "specific_impulse_s": 4170,
        "thrust_mn": 237,
        "mass_flow_mg_s": 5.8,
        "beam_voltage_v": 1800,
        "propellant": "Xenon",
    },
    "AEPS/HERMeS Hall class": {
        "family": "Hall effect",
        "power_w": 12500,
        "efficiency": 0.55,
        "specific_impulse_s": 2900,
        "thrust_mn": 600,
        "beam_voltage_v": 600,
        "propellant": "Xenon",
        "magnetic_field_t": 0.02,
        "channel_length_m": 0.04,
    },
    "SPT-140 Hall class": {
        "family": "Hall effect",
        "power_w": 4500,
        "efficiency": 0.55,
        "specific_impulse_s": 1800,
        "thrust_mn": 280,
        "beam_voltage_v": 300,
        "propellant": "Xenon",
    },
    "CubeSat electrospray estimate": {
        "family": "Electrospray/FEEP/colloid",
        "power_w": 20,
        "efficiency": 0.45,
        "specific_impulse_s": 1200,
        "thrust_mn": 0.8,
        "mass_flow_mg_s": 0.000068,
        "propellant": "Cesium",
    },
}


FUSION_FUELS = {
    "D-T, 17.6 MeV": {
        "energy_j_kg": 3.39e14,
        "charged_fraction": 0.20,
        "note": "High neutron fraction; easier ignition physics than aneutronic fuels, but shielding and radiator loads are severe.",
    },
    "D-He3, 18.3 MeV": {
        "energy_j_kg": 3.53e14,
        "charged_fraction": 0.95,
        "note": "Often used in Direct Fusion Drive studies; helium-3 supply is a major practical issue.",
    },
    "D-D, mixed branches": {
        "energy_j_kg": 8.8e13,
        "charged_fraction": 0.65,
        "note": "No rare helium-3 required, but neutron production and ignition difficulty remain important.",
    },
    "p-B11, 8.7 MeV": {
        "energy_j_kg": 7.0e13,
        "charged_fraction": 0.99,
        "note": "Aneutronic in idealized reaction products, but extremely difficult plasma conditions.",
    },
    "Antimatter annihilation, ideal": {
        "energy_j_kg": C_LIGHT * C_LIGHT,
        "charged_fraction": 0.50,
        "note": "Speculative storage and production problem; energy density assumes combined matter plus antimatter mass.",
    },
}


def safe_float(value, default=0.0):
    try:
        text = str(value).strip()
        if text == "":
            return default
        return float(text)
    except (TypeError, ValueError):
        return default


def fmt(value, unit="", sig=6):
    if value is None or not math.isfinite(value):
        return "n/a"
    if abs(value) >= 1e5 or (0 < abs(value) < 1e-3):
        text = f"{value:.{sig}e}"
    else:
        text = f"{value:.{sig}g}"
    return f"{text} {unit}".rstrip()


def section(title):
    return f"\n{title}\n" + "-" * len(title) + "\n"


def propellant_mass_kg(propellant_name):
    return PROPELLANTS.get(propellant_name, PROPELLANTS["Xenon"]) * AMU


def ion_velocity_from_voltage(voltage_v, charge_state, particle_mass_kg):
    if voltage_v <= 0 or charge_state <= 0 or particle_mass_kg <= 0:
        return 0.0
    return math.sqrt(2.0 * charge_state * E_CHARGE * voltage_v / particle_mass_kg)


def rocket_delta_v(ve, wet_mass, propellant_mass):
    if ve <= 0 or wet_mass <= 0 or propellant_mass <= 0 or propellant_mass >= wet_mass:
        return 0.0
    dry_mass = wet_mass - propellant_mass
    return ve * math.log(wet_mass / dry_mass)


def propellant_for_delta_v(ve, initial_mass, delta_v):
    if ve <= 0 or initial_mass <= 0 or delta_v <= 0:
        return 0.0
    return initial_mass * (1.0 - math.exp(-delta_v / ve))


def time_text(seconds):
    if seconds <= 0 or not math.isfinite(seconds):
        return "n/a"
    days = seconds / 86400.0
    years = days / 365.25
    if years >= 1:
        return f"{seconds:.3g} s ({days:.3g} days, {years:.3g} years)"
    if days >= 1:
        return f"{seconds:.3g} s ({days:.3g} days)"
    if seconds >= 3600:
        return f"{seconds:.3g} s ({seconds / 3600.0:.3g} hours)"
    return f"{seconds:.3g} s"


def electric_thruster_calculation(inputs):
    propellant = inputs["propellant"]
    particle_mass = propellant_mass_kg(propellant)
    z = max(inputs["charge_state"], 1.0)
    power = inputs["power_w"]
    efficiency = max(inputs["efficiency"], 0.0)
    beam_voltage = inputs["beam_voltage_v"]
    isp_input = inputs["specific_impulse_s"]
    mdot_input = inputs["mass_flow_mg_s"] * 1e-6
    thrust_input = inputs["thrust_mn"] * 1e-3
    divergence_deg = inputs["divergence_deg"]
    divergence_eff = math.cos(math.radians(divergence_deg)) if abs(divergence_deg) < 90 else 0.0
    util = max(inputs["propellant_utilization"], 0.0)
    correction = divergence_eff * util
    n = max(inputs["number_thrusters"], 1.0)
    duty = max(inputs["duty_cycle"], 0.0)

    voltage_ve = ion_velocity_from_voltage(beam_voltage, z, particle_mass)
    voltage_isp = voltage_ve / G0 if voltage_ve > 0 else 0.0
    ve = isp_input * G0 if isp_input > 0 else voltage_ve
    isp = ve / G0 if ve > 0 else 0.0

    thrust_per = 0.0
    source = "insufficient inputs"
    mdot_per = mdot_input
    if thrust_input > 0:
        thrust_per = thrust_input
        source = "user-entered thrust"
        if mdot_per <= 0 and ve > 0:
            mdot_per = thrust_per / ve
    elif mdot_per > 0 and ve > 0:
        thrust_per = mdot_per * ve * correction
        source = "mass flow x exhaust velocity x corrections"
    elif power > 0 and efficiency > 0 and ve > 0:
        thrust_per = 2.0 * efficiency * power / ve * correction
        source = "power-limited electric propulsion relation"
        mdot_per = thrust_per / ve if ve > 0 else 0.0

    total_thrust = thrust_per * n * duty
    total_mdot = mdot_per * n * duty
    jet_power = 0.5 * mdot_per * ve * ve if mdot_per > 0 and ve > 0 else 0.0
    thrust_power_eff = thrust_per * thrust_per / (2.0 * mdot_per * power) if thrust_per > 0 and mdot_per > 0 and power > 0 else 0.0
    beam_current = mdot_per / particle_mass * z * E_CHARGE if mdot_per > 0 else 0.0
    discharge_current = power / beam_voltage if power > 0 and beam_voltage > 0 else 0.0
    particles_per_s = mdot_per / particle_mass if mdot_per > 0 else 0.0
    thrust_to_power = thrust_per / power if power > 0 else 0.0
    wet_mass = inputs["spacecraft_mass_kg"]
    prop_mass = inputs["propellant_mass_kg"]
    target_dv = inputs["target_delta_v_m_s"]
    acceleration = total_thrust / wet_mass if total_thrust > 0 and wet_mass > 0 else 0.0
    dv_from_prop = rocket_delta_v(ve, wet_mass, prop_mass)
    prop_for_target = propellant_for_delta_v(ve, wet_mass, target_dv)
    burn_time_prop = prop_mass / total_mdot if prop_mass > 0 and total_mdot > 0 else 0.0
    burn_time_target = prop_for_target / total_mdot if prop_for_target > 0 and total_mdot > 0 else 0.0
    total_impulse = total_thrust * burn_time_prop if burn_time_prop > 0 else 0.0
    power_total = power * n / max(inputs["ppu_efficiency"], 1e-9)
    waste_heat = max(power_total - jet_power * n, 0.0) if power_total > 0 else 0.0

    area = math.pi * max(inputs["channel_outer_radius_m"], 0.0) ** 2 - math.pi * max(inputs["channel_inner_radius_m"], 0.0) ** 2
    thrust_density = thrust_per / area if thrust_per > 0 and area > 0 else 0.0
    channel_length = inputs["channel_length_m"]
    electric_field = beam_voltage / channel_length if beam_voltage > 0 and channel_length > 0 else 0.0
    magnetic_field = inputs["magnetic_field_t"]
    exb_drift = electric_field / magnetic_field if electric_field > 0 and magnetic_field > 0 else 0.0
    electron_cyclotron = E_CHARGE * magnetic_field / ME if magnetic_field > 0 else 0.0
    electron_temp_ev = inputs["electron_temp_ev"]
    electron_thermal_v = math.sqrt(2 * electron_temp_ev * E_CHARGE / ME) if electron_temp_ev > 0 else 0.0
    electron_larmor = electron_thermal_v / electron_cyclotron if electron_thermal_v > 0 and electron_cyclotron > 0 else 0.0
    density = inputs["plasma_density_m3"]
    debye = math.sqrt(EPS0 * electron_temp_ev / (density * E_CHARGE)) if density > 0 and electron_temp_ev > 0 else 0.0

    grid_gap = inputs["grid_gap_m"]
    open_area = inputs["grid_open_area_m2"]
    if beam_voltage > 0 and grid_gap > 0:
        j_cl = (4.0 / 9.0) * EPS0 * math.sqrt(2.0 * z * E_CHARGE / particle_mass) * beam_voltage ** 1.5 / grid_gap ** 2
    else:
        j_cl = 0.0
    i_cl = j_cl * open_area if j_cl > 0 and open_area > 0 else 0.0
    mdot_cl = i_cl * particle_mass / (z * E_CHARGE) if i_cl > 0 else 0.0
    thrust_cl = mdot_cl * voltage_ve if mdot_cl > 0 and voltage_ve > 0 else 0.0

    lines = []
    lines.append(section("Selected model"))
    lines.append(f"Family: {inputs['family']}\n")
    lines.append(f"Propellant: {propellant}, particle mass: {fmt(particle_mass, 'kg')}\n")
    lines.append(f"Thrust source: {source}\n")

    lines.append(section("Core thruster performance"))
    lines.append(f"Voltage-derived exhaust velocity: {fmt(voltage_ve, 'm/s')}\n")
    lines.append(f"Voltage-derived Isp: {fmt(voltage_isp, 's')}\n")
    lines.append(f"Effective exhaust velocity used: {fmt(ve, 'm/s')}\n")
    lines.append(f"Specific impulse used: {fmt(isp, 's')}\n")
    lines.append(f"Per-thruster thrust: {fmt(thrust_per, 'N')} ({fmt(thrust_per * 1000, 'mN')})\n")
    lines.append(f"Total thrust after thruster count and duty cycle: {fmt(total_thrust, 'N')}\n")
    lines.append(f"Per-thruster mass flow: {fmt(mdot_per, 'kg/s')} ({fmt(mdot_per * 1e6, 'mg/s')})\n")
    lines.append(f"Total mass flow: {fmt(total_mdot, 'kg/s')}\n")
    lines.append(f"Thrust-to-power: {fmt(thrust_to_power * 1000, 'mN/kW')}\n")
    lines.append(f"Jet kinetic power: {fmt(jet_power, 'W')}\n")
    lines.append(f"Back-calculated thrust efficiency: {fmt(thrust_power_eff * 100, '%')}\n")
    lines.append(f"Estimated total bus power with PPU efficiency: {fmt(power_total, 'W')}\n")
    lines.append(f"Estimated waste heat: {fmt(waste_heat, 'W')}\n")

    lines.append(section("Particle and electrical quantities"))
    lines.append(f"Particle flow: {fmt(particles_per_s, 'particles/s')}\n")
    lines.append(f"Ion beam current from mass flow: {fmt(beam_current, 'A')}\n")
    lines.append(f"Discharge/beam supply current from P/V: {fmt(discharge_current, 'A')}\n")
    lines.append(f"Correction factor from divergence and utilization: {fmt(correction)}\n")

    lines.append(section("Hall/plasma diagnostics"))
    lines.append(f"Channel electric field: {fmt(electric_field, 'V/m')}\n")
    lines.append(f"E cross B drift estimate: {fmt(exb_drift, 'm/s')}\n")
    lines.append(f"Electron cyclotron angular frequency: {fmt(electron_cyclotron, 'rad/s')}\n")
    lines.append(f"Electron thermal speed: {fmt(electron_thermal_v, 'm/s')}\n")
    lines.append(f"Electron Larmor radius: {fmt(electron_larmor, 'm')}\n")
    lines.append(f"Debye length estimate: {fmt(debye, 'm')}\n")
    lines.append(f"Channel annulus area: {fmt(area, 'm^2')}\n")
    lines.append(f"Thrust density: {fmt(thrust_density, 'N/m^2')}\n")

    lines.append(section("Gridded-ion Child-Langmuir estimate"))
    lines.append(f"Current density limit: {fmt(j_cl, 'A/m^2')}\n")
    lines.append(f"Total ion current limit: {fmt(i_cl, 'A')}\n")
    lines.append(f"Mass-flow limit from grid area: {fmt(mdot_cl, 'kg/s')}\n")
    lines.append(f"Voltage-only thrust limit: {fmt(thrust_cl, 'N')}\n")

    lines.append(section("Mission-level estimates"))
    lines.append(f"Initial spacecraft mass: {fmt(wet_mass, 'kg')}\n")
    lines.append(f"Propellant mass: {fmt(prop_mass, 'kg')}\n")
    lines.append(f"Initial acceleration: {fmt(acceleration, 'm/s^2')} ({fmt(acceleration / G0, 'g0')})\n")
    lines.append(f"Delta-v from entered propellant: {fmt(dv_from_prop, 'm/s')}\n")
    lines.append(f"Propellant needed for target delta-v: {fmt(prop_for_target, 'kg')}\n")
    lines.append(f"Burn time using entered propellant: {time_text(burn_time_prop)}\n")
    lines.append(f"Burn time for target delta-v propellant: {time_text(burn_time_target)}\n")
    lines.append(f"Total impulse from entered propellant burn: {fmt(total_impulse, 'N*s')}\n")
    return "".join(lines)


def pulsed_mpd_calculation(inputs):
    cap_f = inputs["capacitor_uf"] * 1e-6
    voltage = inputs["charge_voltage_v"]
    rate = inputs["rep_rate_hz"]
    mass_bit = inputs["mass_bit_ug"] * 1e-9
    ve = inputs["exhaust_velocity_km_s"] * 1000.0
    impulse_bit_input = inputs["impulse_bit_uns"] * 1e-6
    pulse_energy = inputs["pulse_energy_j"] if inputs["pulse_energy_j"] > 0 else 0.5 * cap_f * voltage * voltage
    impulse_bit = impulse_bit_input if impulse_bit_input > 0 else mass_bit * ve
    thrust = impulse_bit * rate
    mdot = mass_bit * rate
    isp = impulse_bit / (mass_bit * G0) if impulse_bit > 0 and mass_bit > 0 else 0.0
    average_power = pulse_energy * rate
    eta_pulse = impulse_bit * impulse_bit / (2 * mass_bit * pulse_energy) if impulse_bit > 0 and mass_bit > 0 and pulse_energy > 0 else 0.0
    wet_mass = inputs["spacecraft_mass_kg"]
    prop_mass = inputs["propellant_mass_kg"]
    dv = rocket_delta_v(isp * G0, wet_mass, prop_mass)
    pulses_total = prop_mass / mass_bit if prop_mass > 0 and mass_bit > 0 else 0.0
    burn_time = pulses_total / rate if pulses_total > 0 and rate > 0 else 0.0

    current = inputs["mpd_current_a"]
    ra = inputs["anode_radius_m"]
    rc = inputs["cathode_radius_m"]
    mpd_mdot = inputs["mpd_mass_flow_mg_s"] * 1e-6
    mpd_power = inputs["mpd_power_w"]
    applied_b = inputs["applied_field_t"]
    length = inputs["mpd_length_m"]
    geom = math.log(ra / rc) + 0.75 if ra > rc and rc > 0 else 0.0
    self_field_thrust = MU0 / (4 * math.pi) * current * current * geom if current > 0 and geom > 0 else 0.0
    applied_field_thrust = current * applied_b * length if current > 0 and applied_b > 0 and length > 0 else 0.0
    mpd_thrust = self_field_thrust + applied_field_thrust
    mpd_ve = mpd_thrust / mpd_mdot if mpd_thrust > 0 and mpd_mdot > 0 else 0.0
    mpd_isp = mpd_ve / G0 if mpd_ve > 0 else 0.0
    mpd_eff = mpd_thrust * mpd_thrust / (2 * mpd_mdot * mpd_power) if mpd_thrust > 0 and mpd_mdot > 0 and mpd_power > 0 else 0.0

    lines = []
    lines.append(section("Pulsed plasma / pulsed inductive estimate"))
    lines.append(f"Capacitor energy per pulse: {fmt(pulse_energy, 'J')}\n")
    lines.append(f"Repetition rate: {fmt(rate, 'Hz')}\n")
    lines.append(f"Average power: {fmt(average_power, 'W')}\n")
    lines.append(f"Mass bit: {fmt(mass_bit, 'kg')}\n")
    lines.append(f"Impulse bit used: {fmt(impulse_bit, 'N*s')}\n")
    lines.append(f"Average thrust: {fmt(thrust, 'N')} ({fmt(thrust * 1000, 'mN')})\n")
    lines.append(f"Average mass flow: {fmt(mdot, 'kg/s')}\n")
    lines.append(f"Specific impulse: {fmt(isp, 's')}\n")
    lines.append(f"Pulse efficiency estimate: {fmt(eta_pulse * 100, '%')}\n")
    lines.append(f"Total available pulses: {fmt(pulses_total)}\n")
    lines.append(f"Burn time from entered propellant: {time_text(burn_time)}\n")
    lines.append(f"Delta-v from entered propellant: {fmt(dv, 'm/s')}\n")

    lines.append(section("Steady MPD rough estimate"))
    lines.append("Self-field MPD uses a Maecker-style geometry estimate; use for early sizing only.\n")
    lines.append(f"Geometry factor ln(ra/rc)+0.75: {fmt(geom)}\n")
    lines.append(f"Self-field thrust: {fmt(self_field_thrust, 'N')}\n")
    lines.append(f"Applied-field Lorentz thrust IBL: {fmt(applied_field_thrust, 'N')}\n")
    lines.append(f"Total MPD thrust estimate: {fmt(mpd_thrust, 'N')}\n")
    lines.append(f"MPD exhaust velocity: {fmt(mpd_ve, 'm/s')}\n")
    lines.append(f"MPD Isp: {fmt(mpd_isp, 's')}\n")
    lines.append(f"MPD back-calculated efficiency: {fmt(mpd_eff * 100, '%')}\n")
    return "".join(lines)


def sail_tether_calculation(inputs):
    area = inputs["sail_area_m2"]
    eff = inputs["sail_efficiency"]
    angle = math.radians(inputs["sail_angle_deg"])
    distance_au = max(inputs["solar_distance_au"], 1e-9)
    mass = inputs["spacecraft_mass_kg"]
    pressure_1au = 9.08e-6
    sail_force = pressure_1au * eff * area * max(math.cos(angle), 0.0) ** 2 / (distance_au * distance_au)
    sail_acc = sail_force / mass if mass > 0 else 0.0
    areal_density = inputs["areal_density_g_m2"]
    characteristic_acc = (pressure_1au * eff) / (areal_density / 1000.0) if areal_density > 0 else 0.0
    coast_days = inputs["sail_days"]
    ideal_speed_gain = sail_acc * coast_days * 86400.0 if coast_days > 0 else 0.0

    beam_power = inputs["laser_power_w"]
    photon_factor = inputs["photon_momentum_factor"]
    laser_eff = inputs["laser_coupling_efficiency"]
    laser_force = photon_factor * laser_eff * beam_power / C_LIGHT if beam_power > 0 else 0.0
    laser_acc = laser_force / mass if mass > 0 else 0.0

    tether_current = inputs["tether_current_a"]
    tether_length = inputs["tether_length_m"]
    magnetic_field = inputs["tether_b_t"]
    tether_angle = math.radians(inputs["tether_angle_deg"])
    orbital_velocity = inputs["orbital_velocity_m_s"]
    tether_resistance = inputs["tether_resistance_ohm"]
    tether_force = tether_current * tether_length * magnetic_field * math.sin(tether_angle)
    tether_emf = orbital_velocity * magnetic_field * tether_length * math.sin(tether_angle)
    ohmic_loss = tether_current * tether_current * tether_resistance if tether_resistance > 0 else 0.0
    tether_power = tether_current * tether_emf
    tether_acc = tether_force / mass if mass > 0 else 0.0

    lines = []
    lines.append(section("Solar sail"))
    lines.append(f"Radiation pressure at 1 AU, perfect reflector baseline: {fmt(pressure_1au, 'N/m^2')}\n")
    lines.append(f"Sail force: {fmt(sail_force, 'N')}\n")
    lines.append(f"Sail acceleration: {fmt(sail_acc, 'm/s^2')} ({fmt(sail_acc / G0, 'g0')})\n")
    lines.append(f"Characteristic acceleration from areal density: {fmt(characteristic_acc, 'm/s^2')}\n")
    lines.append(f"Ideal speed gain after entered duration: {fmt(ideal_speed_gain, 'm/s')}\n")

    lines.append(section("Laser / photon sail"))
    lines.append(f"Photon sail force: {fmt(laser_force, 'N')}\n")
    lines.append(f"Photon sail acceleration: {fmt(laser_acc, 'm/s^2')}\n")
    lines.append(f"Beam power per newton of force: {fmt(beam_power / laser_force if laser_force > 0 else 0, 'W/N')}\n")

    lines.append(section("Electrodynamic tether"))
    lines.append(f"Lorentz force I L B sin(theta): {fmt(tether_force, 'N')}\n")
    lines.append(f"Motional EMF v B L sin(theta): {fmt(tether_emf, 'V')}\n")
    lines.append(f"Electrical power at entered current and EMF: {fmt(tether_power, 'W')}\n")
    lines.append(f"Ohmic loss in tether: {fmt(ohmic_loss, 'W')}\n")
    lines.append(f"Tether acceleration: {fmt(tether_acc, 'm/s^2')}\n")
    return "".join(lines)


def experimental_fusion_calculation(inputs):
    fuel_name = inputs["fusion_fuel"]
    fuel = FUSION_FUELS.get(fuel_name, FUSION_FUELS["D-He3, 18.3 MeV"])
    energy_density = fuel["energy_j_kg"]
    burnup = max(inputs["burnup_fraction"], 1e-12)
    fusion_power = inputs["fusion_power_mw"] * 1e6
    entered_fuel_flow = inputs["fusion_fuel_flow_mg_s"] * 1e-6
    if fusion_power <= 0 and entered_fuel_flow > 0:
        fusion_power = entered_fuel_flow * energy_density * burnup
        power_source = "computed from entered fusion fuel flow"
    else:
        power_source = "user-entered fusion power"

    fuel_flow = fusion_power / (energy_density * burnup) if fusion_power > 0 else 0.0
    charged_fraction = inputs["charged_particle_fraction"] if inputs["charged_particle_fraction"] > 0 else fuel["charged_fraction"]
    charged_fraction = min(max(charged_fraction, 0.0), 1.0)
    neutron_fraction = max(1.0 - charged_fraction, 0.0)
    nozzle_eff = min(max(inputs["magnetic_nozzle_efficiency"], 0.0), 1.0)
    thermal_coupling = min(max(inputs["neutron_thermal_coupling"], 0.0), 1.0)
    electric_eff = min(max(inputs["electric_conversion_efficiency"], 0.0), 1.0)
    recirc = min(max(inputs["recirculating_power_fraction"], 0.0), 1.0)

    charged_power = fusion_power * charged_fraction
    neutron_power = fusion_power * neutron_fraction
    direct_jet_power = charged_power * nozzle_eff + neutron_power * thermal_coupling * nozzle_eff
    electric_power = charged_power * electric_eff
    recirculating_power = fusion_power * recirc
    net_electric_power = max(electric_power - recirculating_power, 0.0)

    aux_mdot = inputs["aux_propellant_kg_s"]
    target_isp = inputs["target_isp_s"]
    if target_isp > 0:
        ve = target_isp * G0
        total_exhaust_mdot = 2.0 * direct_jet_power / (ve * ve) if direct_jet_power > 0 else 0.0
        thrust = total_exhaust_mdot * ve
        mode_note = "target Isp sets exhaust velocity; required exhaust mass flow is computed from jet power"
    elif aux_mdot > 0:
        total_exhaust_mdot = aux_mdot + fuel_flow
        ve = math.sqrt(2.0 * direct_jet_power / total_exhaust_mdot) if direct_jet_power > 0 and total_exhaust_mdot > 0 else 0.0
        thrust = total_exhaust_mdot * ve
        mode_note = "entered propellant flow sets exhaust mass flow; exhaust velocity is computed from jet power"
    else:
        ve = 0.0
        total_exhaust_mdot = 0.0
        thrust = 0.0
        mode_note = "enter target Isp or auxiliary propellant flow to close the thrust calculation"

    isp = ve / G0 if ve > 0 else 0.0
    required_aux_mdot = max(total_exhaust_mdot - fuel_flow, 0.0)
    jet_power_check = 0.5 * total_exhaust_mdot * ve * ve if total_exhaust_mdot > 0 else 0.0
    thrust_to_power = thrust / fusion_power if fusion_power > 0 else 0.0

    waste_heat = max(
        fusion_power - direct_jet_power - net_electric_power,
        0.0,
    )
    radiator_temp = inputs["radiator_temp_k"]
    emissivity = min(max(inputs["radiator_emissivity"], 1e-9), 1.0)
    radiator_area = waste_heat / (emissivity * SIGMA_SB * radiator_temp ** 4) if waste_heat > 0 and radiator_temp > 0 else 0.0
    radiator_mass = radiator_area * inputs["radiator_areal_density_kg_m2"] if radiator_area > 0 else 0.0

    wet_mass = inputs["spacecraft_mass_kg"]
    prop_mass = inputs["reaction_propellant_mass_kg"]
    fusion_fuel_mass = inputs["fusion_fuel_mass_kg"]
    target_dv = inputs["target_delta_v_m_s"]
    acceleration = thrust / wet_mass if thrust > 0 and wet_mass > 0 else 0.0
    reaction_burn_time = prop_mass / required_aux_mdot if prop_mass > 0 and required_aux_mdot > 0 else 0.0
    fuel_burn_time = fusion_fuel_mass / fuel_flow if fusion_fuel_mass > 0 and fuel_flow > 0 else 0.0
    practical_burn_time = min(t for t in [reaction_burn_time, fuel_burn_time] if t > 0) if reaction_burn_time > 0 or fuel_burn_time > 0 else 0.0
    dv_from_reaction_prop = rocket_delta_v(ve, wet_mass, prop_mass) if ve > 0 else 0.0
    prop_for_target = propellant_for_delta_v(ve, wet_mass, target_dv) if ve > 0 else 0.0
    pulse_energy = inputs["pulse_energy_gj"] * 1e9
    pulse_rate = inputs["pulse_rate_hz"]
    pulse_jet_fraction = min(max(inputs["pulse_jet_fraction"], 0.0), 1.0)
    pellet_mass = inputs["pellet_mass_mg"] * 1e-6
    pulse_power = pulse_energy * pulse_rate
    pulse_jet_power = pulse_power * pulse_jet_fraction
    pulse_fuel_flow = pellet_mass * pulse_rate
    pulse_ve = inputs["pulse_exhaust_velocity_km_s"] * 1000.0
    pulse_mdot = inputs["pulse_exhaust_mass_kg"] * pulse_rate
    pulse_thrust = pulse_mdot * pulse_ve if pulse_mdot > 0 and pulse_ve > 0 else 2.0 * pulse_jet_power / pulse_ve if pulse_jet_power > 0 and pulse_ve > 0 else 0.0
    pulse_impulse_bit = pulse_thrust / pulse_rate if pulse_rate > 0 else 0.0
    pulse_isp = pulse_ve / G0 if pulse_ve > 0 else 0.0

    lightsail_power = inputs["beam_power_gw"] * 1e9
    lightsail_eff = min(max(inputs["beam_coupling_efficiency"], 0.0), 1.0)
    lightsail_factor = inputs["beam_momentum_factor"]
    lightsail_force = lightsail_factor * lightsail_eff * lightsail_power / C_LIGHT if lightsail_power > 0 else 0.0
    lightsail_acc = lightsail_force / wet_mass if wet_mass > 0 else 0.0

    lines = []
    lines.append(section("Fusion / antimatter concept model"))
    lines.append(f"Fuel cycle: {fuel_name}\n")
    lines.append(f"Note: {fuel['note']}\n")
    lines.append(f"Energy density: {fmt(energy_density, 'J/kg')}\n")
    lines.append(f"Fusion power source: {power_source}\n")
    lines.append(f"Fusion power: {fmt(fusion_power, 'W')}\n")
    lines.append(f"Fusion fuel burn rate: {fmt(fuel_flow, 'kg/s')} ({fmt(fuel_flow * 1e6, 'mg/s')})\n")
    lines.append(f"Charged-particle power: {fmt(charged_power, 'W')}\n")
    lines.append(f"Neutron / neutral power: {fmt(neutron_power, 'W')}\n")
    lines.append(f"Direct jet power after coupling/nozzle losses: {fmt(direct_jet_power, 'W')}\n")
    lines.append(f"Net electric power estimate: {fmt(net_electric_power, 'W')}\n")
    lines.append(f"Calculation closure: {mode_note}\n")

    lines.append(section("Propulsive performance"))
    lines.append(f"Exhaust velocity: {fmt(ve, 'm/s')}\n")
    lines.append(f"Specific impulse: {fmt(isp, 's')}\n")
    lines.append(f"Total exhaust mass flow: {fmt(total_exhaust_mdot, 'kg/s')}\n")
    lines.append(f"Required auxiliary/reaction propellant flow: {fmt(required_aux_mdot, 'kg/s')}\n")
    lines.append(f"Thrust: {fmt(thrust, 'N')}\n")
    lines.append(f"Thrust-to-fusion-power: {fmt(thrust_to_power * 1e6, 'N/MW')}\n")
    lines.append(f"Jet power check: {fmt(jet_power_check, 'W')}\n")
    lines.append(f"Initial acceleration: {fmt(acceleration, 'm/s^2')} ({fmt(acceleration / G0, 'g0')})\n")

    lines.append(section("Thermal / radiator sizing"))
    lines.append(f"Rejected heat estimate: {fmt(waste_heat, 'W')}\n")
    lines.append(f"Radiator temperature: {fmt(radiator_temp, 'K')}\n")
    lines.append(f"Radiator area: {fmt(radiator_area, 'm^2')}\n")
    lines.append(f"Radiator mass estimate: {fmt(radiator_mass, 'kg')}\n")

    lines.append(section("Mission sizing"))
    lines.append(f"Reaction propellant burn time: {time_text(reaction_burn_time)}\n")
    lines.append(f"Fusion fuel burn time: {time_text(fuel_burn_time)}\n")
    lines.append(f"Practical burn time limit: {time_text(practical_burn_time)}\n")
    lines.append(f"Delta-v from reaction propellant mass: {fmt(dv_from_reaction_prop, 'm/s')}\n")
    lines.append(f"Reaction propellant needed for target delta-v: {fmt(prop_for_target, 'kg')}\n")

    lines.append(section("Pulsed fusion / nuclear pulse rough model"))
    lines.append(f"Pulse energy: {fmt(pulse_energy, 'J')}\n")
    lines.append(f"Pulse rate: {fmt(pulse_rate, 'Hz')}\n")
    lines.append(f"Average pulse power: {fmt(pulse_power, 'W')}\n")
    lines.append(f"Pellet/fuel flow: {fmt(pulse_fuel_flow, 'kg/s')}\n")
    lines.append(f"Pulse-mode thrust: {fmt(pulse_thrust, 'N')}\n")
    lines.append(f"Impulse bit: {fmt(pulse_impulse_bit, 'N*s')}\n")
    lines.append(f"Pulse-mode Isp: {fmt(pulse_isp, 's')}\n")

    lines.append(section("Beamed interstellar-style comparison"))
    lines.append(f"External beam force: {fmt(lightsail_force, 'N')}\n")
    lines.append(f"External beam acceleration: {fmt(lightsail_acc, 'm/s^2')}\n")
    return "".join(lines)


class ScrollFrame(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent)
        self.canvas = tk.Canvas(self, highlightthickness=0, background="#10161f")
        self.scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.inner = ttk.Frame(self.canvas)
        self.inner.bind("<Configure>", lambda _event: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.window = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.scrollbar.pack(side="right", fill="y")
        self.canvas.bind("<Configure>", self._resize)

    def _resize(self, event):
        self.canvas.itemconfigure(self.window, width=event.width)


class InputPanel:
    def __init__(self, parent):
        self.parent = parent
        self.vars = {}
        self.row = 0

    def heading(self, text):
        label = ttk.Label(self.parent, text=text, font=("Segoe UI", 11, "bold"))
        label.grid(row=self.row, column=0, columnspan=3, sticky="w", padx=10, pady=(14, 4))
        self.row += 1

    def entry(self, key, label, default="", unit=""):
        ttk.Label(self.parent, text=label).grid(row=self.row, column=0, sticky="w", padx=10, pady=3)
        var = tk.StringVar(value=str(default))
        ttk.Entry(self.parent, textvariable=var, width=18).grid(row=self.row, column=1, sticky="ew", padx=6, pady=3)
        ttk.Label(self.parent, text=unit).grid(row=self.row, column=2, sticky="w", padx=4, pady=3)
        self.vars[key] = var
        self.row += 1
        return var

    def combo(self, key, label, values, default):
        ttk.Label(self.parent, text=label).grid(row=self.row, column=0, sticky="w", padx=10, pady=3)
        var = tk.StringVar(value=default)
        box = ttk.Combobox(self.parent, textvariable=var, values=values, state="readonly", width=22)
        box.grid(row=self.row, column=1, columnspan=2, sticky="ew", padx=6, pady=3)
        self.vars[key] = var
        self.row += 1
        return box

    def values(self):
        data = {}
        for key, var in self.vars.items():
            if key in {"family", "propellant", "preset"}:
                data[key] = var.get()
            else:
                data[key] = safe_float(var.get())
        return data

    def set_value(self, key, value):
        if key in self.vars:
            self.vars[key].set(str(value))


class CalculatorTab(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent)
        self.columnconfigure(0, weight=0)
        self.columnconfigure(1, weight=1)
        self.rowconfigure(0, weight=1)
        left = ScrollFrame(self)
        left.grid(row=0, column=0, sticky="nsew")
        self.panel = InputPanel(left.inner)
        self.result = tk.Text(self, wrap="word", font=("Consolas", 10), bg="#0b1117", fg="#e6edf3", insertbackground="#e6edf3")
        self.result.grid(row=0, column=1, sticky="nsew", padx=(10, 0))
        buttons = ttk.Frame(self)
        buttons.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        ttk.Button(buttons, text="Calculate", command=self.calculate).pack(side="left")
        ttk.Button(buttons, text="Save results", command=self.save_results).pack(side="left", padx=8)

    def write_result(self, text):
        self.result.delete("1.0", "end")
        self.result.insert("1.0", text)

    def calculate(self):
        raise NotImplementedError

    def save_results(self):
        text = self.result.get("1.0", "end-1c").strip()
        if not text:
            messagebox.showinfo("Nothing to save", "Run a calculation first.")
            return
        path = filedialog.asksaveasfilename(
            title="Save results",
            defaultextension=".txt",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
        )
        if path:
            Path(path).write_text(text, encoding="utf-8")


class ElectricTab(CalculatorTab):
    def __init__(self, parent):
        super().__init__(parent)
        p = self.panel
        preset_box = p.combo("preset", "Preset", list(ELECTRIC_PRESETS.keys()), "Blank/custom")
        preset_box.bind("<<ComboboxSelected>>", self.apply_preset)
        p.combo("family", "Thruster family", ["Hall effect", "Gridded ion", "Electrospray/FEEP/colloid", "Resistojet/arcjet", "VASIMR/RF plasma", "Generic electric"], "Hall effect")
        p.combo("propellant", "Propellant", list(PROPELLANTS.keys()), "Xenon")

        p.heading("Core inputs")
        p.entry("power_w", "Electrical power per thruster", 5000, "W")
        p.entry("ppu_efficiency", "PPU efficiency", 0.94, "0-1")
        p.entry("efficiency", "Thruster efficiency", 0.55, "0-1")
        p.entry("specific_impulse_s", "Specific impulse override", 1800, "s")
        p.entry("beam_voltage_v", "Beam/discharge voltage", 300, "V")
        p.entry("mass_flow_mg_s", "Mass flow per thruster", "", "mg/s")
        p.entry("thrust_mn", "Known thrust override", "", "mN")
        p.entry("charge_state", "Ion charge state", 1, "Z")
        p.entry("divergence_deg", "Plume half-angle correction", 0, "deg")
        p.entry("propellant_utilization", "Propellant utilization", 1.0, "0-1")
        p.entry("number_thrusters", "Number of thrusters", 1, "")
        p.entry("duty_cycle", "Duty cycle", 1.0, "0-1")

        p.heading("Mission sizing")
        p.entry("spacecraft_mass_kg", "Initial spacecraft mass", 1000, "kg")
        p.entry("propellant_mass_kg", "Propellant mass", 100, "kg")
        p.entry("target_delta_v_m_s", "Target delta-v", 3000, "m/s")

        p.heading("Hall/plasma diagnostics")
        p.entry("channel_length_m", "Acceleration/channel length", 0.04, "m")
        p.entry("magnetic_field_t", "Magnetic field", 0.02, "T")
        p.entry("electron_temp_ev", "Electron temperature", 10, "eV")
        p.entry("plasma_density_m3", "Plasma density", 1e17, "m^-3")
        p.entry("channel_inner_radius_m", "Channel inner radius", 0.04, "m")
        p.entry("channel_outer_radius_m", "Channel outer radius", 0.08, "m")

        p.heading("Gridded-ion diagnostics")
        p.entry("grid_gap_m", "Grid gap", 0.001, "m")
        p.entry("grid_open_area_m2", "Total open grid area", 0.01, "m^2")
        self.calculate()

    def apply_preset(self, _event=None):
        preset = ELECTRIC_PRESETS.get(self.panel.vars["preset"].get(), {})
        for key, value in preset.items():
            self.panel.set_value(key, value)
        self.calculate()

    def calculate(self):
        self.write_result(electric_thruster_calculation(self.panel.values()))


class PulsedMpdTab(CalculatorTab):
    def __init__(self, parent):
        super().__init__(parent)
        p = self.panel
        p.heading("Pulsed plasma / pulsed inductive")
        p.entry("capacitor_uf", "Capacitance", 3, "uF")
        p.entry("charge_voltage_v", "Charge voltage", 2000, "V")
        p.entry("pulse_energy_j", "Pulse energy override", "", "J")
        p.entry("rep_rate_hz", "Repetition rate", 10, "Hz")
        p.entry("mass_bit_ug", "Mass bit", 10, "ug")
        p.entry("impulse_bit_uns", "Impulse bit override", "", "uN*s")
        p.entry("exhaust_velocity_km_s", "Exhaust velocity", 30, "km/s")
        p.entry("spacecraft_mass_kg", "Initial spacecraft mass", 100, "kg")
        p.entry("propellant_mass_kg", "Propellant mass", 2, "kg")

        p.heading("Steady MPD rough sizing")
        p.entry("mpd_current_a", "Arc/plasma current", 1000, "A")
        p.entry("mpd_mass_flow_mg_s", "Mass flow", 100, "mg/s")
        p.entry("mpd_power_w", "Electrical power", 100000, "W")
        p.entry("anode_radius_m", "Anode radius", 0.05, "m")
        p.entry("cathode_radius_m", "Cathode radius", 0.005, "m")
        p.entry("applied_field_t", "Applied magnetic field", 0.1, "T")
        p.entry("mpd_length_m", "Active length", 0.1, "m")
        self.calculate()

    def calculate(self):
        self.write_result(pulsed_mpd_calculation(self.panel.values()))


class SailTetherTab(CalculatorTab):
    def __init__(self, parent):
        super().__init__(parent)
        p = self.panel
        p.heading("Solar sail")
        p.entry("sail_area_m2", "Sail area", 10000, "m^2")
        p.entry("sail_efficiency", "Sail optical efficiency", 0.9, "0-1")
        p.entry("sail_angle_deg", "Sunline angle", 0, "deg")
        p.entry("solar_distance_au", "Solar distance", 1, "AU")
        p.entry("areal_density_g_m2", "Areal density", 10, "g/m^2")
        p.entry("sail_days", "Acceleration duration", 30, "days")
        p.entry("spacecraft_mass_kg", "Spacecraft mass", 100, "kg")

        p.heading("Laser/photon sail")
        p.entry("laser_power_w", "Beam power", 1000000, "W")
        p.entry("laser_coupling_efficiency", "Coupling efficiency", 0.8, "0-1")
        p.entry("photon_momentum_factor", "Momentum factor", 2, "1 absorbing, 2 reflecting")

        p.heading("Electrodynamic tether")
        p.entry("tether_current_a", "Tether current", 5, "A")
        p.entry("tether_length_m", "Tether length", 5000, "m")
        p.entry("tether_b_t", "Magnetic field", 3e-5, "T")
        p.entry("tether_angle_deg", "Angle to B field", 90, "deg")
        p.entry("orbital_velocity_m_s", "Orbital velocity", 7500, "m/s")
        p.entry("tether_resistance_ohm", "Tether resistance", 10, "ohm")
        self.calculate()

    def calculate(self):
        self.write_result(sail_tether_calculation(self.panel.values()))


class ExperimentalFusionTab(CalculatorTab):
    def __init__(self, parent):
        super().__init__(parent)
        p = self.panel
        p.heading("Direct / steady fusion concept")
        p.combo("fusion_fuel", "Fuel cycle", list(FUSION_FUELS.keys()), "D-He3, 18.3 MeV")
        p.entry("fusion_power_mw", "Fusion power", 100, "MW")
        p.entry("fusion_fuel_flow_mg_s", "Fuel flow override", "", "mg/s")
        p.entry("burnup_fraction", "Fuel burnup fraction", 0.3, "0-1")
        p.entry("charged_particle_fraction", "Charged power fraction override", "", "0-1")
        p.entry("magnetic_nozzle_efficiency", "Magnetic nozzle efficiency", 0.65, "0-1")
        p.entry("neutron_thermal_coupling", "Neutron/neutral thermal coupling", 0.05, "0-1")
        p.entry("electric_conversion_efficiency", "Direct electric conversion", 0.35, "0-1")
        p.entry("recirculating_power_fraction", "Recirculating power fraction", 0.2, "0-1")
        p.entry("target_isp_s", "Target Isp", 10000, "s")
        p.entry("aux_propellant_kg_s", "Auxiliary propellant flow", "", "kg/s")

        p.heading("Thermal / radiator")
        p.entry("radiator_temp_k", "Radiator temperature", 900, "K")
        p.entry("radiator_emissivity", "Radiator emissivity", 0.85, "0-1")
        p.entry("radiator_areal_density_kg_m2", "Radiator areal density", 5, "kg/m^2")

        p.heading("Mission sizing")
        p.entry("spacecraft_mass_kg", "Initial spacecraft mass", 100000, "kg")
        p.entry("reaction_propellant_mass_kg", "Reaction propellant mass", 20000, "kg")
        p.entry("fusion_fuel_mass_kg", "Fusion fuel mass", 1000, "kg")
        p.entry("target_delta_v_m_s", "Target delta-v", 50000, "m/s")

        p.heading("Pulsed fusion / nuclear pulse rough model")
        p.entry("pulse_energy_gj", "Energy per pulse", 1, "GJ")
        p.entry("pulse_rate_hz", "Pulse rate", 0.1, "Hz")
        p.entry("pulse_jet_fraction", "Pulse energy to jet", 0.4, "0-1")
        p.entry("pellet_mass_mg", "Pellet/fuel mass", 10, "mg")
        p.entry("pulse_exhaust_mass_kg", "Exhaust mass per pulse", 0.05, "kg")
        p.entry("pulse_exhaust_velocity_km_s", "Pulse exhaust velocity", 100, "km/s")

        p.heading("Beamed propulsion comparison")
        p.entry("beam_power_gw", "External beam power", 10, "GW")
        p.entry("beam_coupling_efficiency", "Beam coupling efficiency", 0.5, "0-1")
        p.entry("beam_momentum_factor", "Momentum factor", 2, "1 absorbing, 2 reflecting")
        self.calculate()

    def calculate(self):
        self.write_result(experimental_fusion_calculation(self.panel.values()))


class SourcesTab(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent)
        text = tk.Text(self, wrap="word", font=("Consolas", 10), bg="#0b1117", fg="#e6edf3")
        text.pack(fill="both", expand=True)
        notes = """Scope and caveats
-----------------
This is an early-stage engineering calculator for non-chemical in-space propulsion.
It is not a plume solver, thermal model, erosion model, mission optimizer, or
flight qualification tool. Real thruster design needs experiments, plasma
simulation, thermal/structural analysis, contamination analysis, high-voltage
design, power electronics design, and mission trajectory optimization.

Included mechanism families
---------------------------
- Hall-effect electric propulsion
- Gridded electrostatic ion propulsion
- Electrospray, FEEP, and colloid micropropulsion as generic electrostatic thrusters
- Electrothermal resistojet/arcjet as generic power-to-exhaust-velocity devices
- RF/VASIMR-like plasma propulsion as generic electric propulsion
- Pulsed plasma and pulsed inductive thrusters
- Magnetoplasmadynamic thrusters
- Solar sails
- Laser/photon sails
- Electrodynamic tethers
- Experimental direct fusion, pulsed fusion, nuclear-pulse-style, and ideal
  antimatter comparison models

Core equations used
-------------------
F = mdot * ve
Isp = ve / g0
F = 2 * eta * P / ve = 2 * eta * P / (g0 * Isp)
delta-v = ve * ln(m0 / m1)
ve_ion = sqrt(2 * Z * e * V / m_i)
Child-Langmuir J = (4/9) eps0 * sqrt(2q/m) * V^(3/2) / d^2
Pulsed energy E = 0.5 * C * V^2
Pulsed average thrust = impulse_bit * repetition_rate
Solar sail force = 9.08e-6 * efficiency * area * cos(angle)^2 / AU_distance^2
Photon sail force = momentum_factor * efficiency * beam_power / c
Electrodynamic tether force = I * L * B * sin(theta)
Fusion fuel flow = fusion_power / (fuel_energy_density * burnup_fraction)
Fusion jet power = charged_power * nozzle_efficiency + captured_neutral_power
Fusion thrust closure = 2 * jet_power / ve when target Isp is entered
Radiator area = waste_heat / (emissivity * sigma_SB * T^4)

Representative references searched
----------------------------------
- NASA/Glenn and JPL literature on NSTAR, NEXT, and solar electric propulsion.
- NASA/TM-2018-219761 / IEPC-2017 AEPS overview for Hall-thruster class data.
- Goebel and Katz, Fundamentals of Electric Propulsion: Ion and Hall Thrusters.
- Choueiri, Scientific American 2009, and MPD literature for electromagnetic thruster ranges.
- NASA tether handbook / electrodynamic tether references for Lorentz-force sizing.
- Solar sail literature using the 1 AU reflective pressure baseline near 9.08 uN/m^2.
- Recent arXiv/paper abstracts for oscillating plasma thrusters, electrospray plume
  impingement, liquid-fed PPTs, hydromagnetic pulsed thrusters, and MPD reviews.
- Direct Fusion Drive, magneto-inertial fusion rocket, and pulsed fission-fusion
  concept papers and NASA NIAC summaries for speculative nuclear propulsion.

Use the output as a sizing compass, not as a final design authority.
"""
        text.insert("1.0", notes)
        text.configure(state="disabled")


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Non-Chemical Space Propulsion Calculator")
        self.geometry("1180x780")
        self.minsize(1000, 640)
        self.configure(bg="#10161f")
        self._style()
        self._build()

    def _style(self):
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure(".", background="#10161f", foreground="#e6edf3", fieldbackground="#111b26")
        style.configure("TLabel", background="#10161f", foreground="#d6e2ef")
        style.configure("TFrame", background="#10161f")
        style.configure("TButton", padding=8, background="#18324a", foreground="#e6edf3", borderwidth=0)
        style.map("TButton", background=[("active", "#224563")])
        style.configure("TEntry", fieldbackground="#0b1117", foreground="#e6edf3", insertcolor="#e6edf3")
        style.configure("TCombobox", fieldbackground="#0b1117", foreground="#e6edf3")
        style.configure("TNotebook", background="#10161f", borderwidth=0)
        style.configure("TNotebook.Tab", padding=(12, 8), background="#182230", foreground="#d6e2ef")
        style.map("TNotebook.Tab", background=[("selected", "#23364a")])

    def _build(self):
        header = ttk.Frame(self)
        header.pack(fill="x", padx=14, pady=12)
        ttk.Label(header, text="Non-Chemical Space Propulsion Calculator", font=("Segoe UI", 18, "bold")).pack(side="left")
        ttk.Button(header, text="Export input snapshot", command=self.export_snapshot).pack(side="right")

        notebook = ttk.Notebook(self)
        notebook.pack(fill="both", expand=True, padx=14, pady=(0, 14))
        self.electric = ElectricTab(notebook)
        self.pulsed = PulsedMpdTab(notebook)
        self.sail = SailTetherTab(notebook)
        self.experimental = ExperimentalFusionTab(notebook)
        self.sources = SourcesTab(notebook)
        notebook.add(self.electric, text="Hall / Ion / Electric")
        notebook.add(self.pulsed, text="Pulsed / MPD")
        notebook.add(self.sail, text="Sail / Tether")
        notebook.add(self.experimental, text="Experimental / Fusion")
        notebook.add(self.sources, text="Sources / Notes")

    def export_snapshot(self):
        snapshot = {
            "electric": self.electric.panel.values(),
            "pulsed_mpd": self.pulsed.panel.values(),
            "sail_tether": self.sail.panel.values(),
            "experimental_fusion": self.experimental.panel.values(),
        }
        path = filedialog.asksaveasfilename(
            title="Export input snapshot",
            defaultextension=".json",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
        )
        if path:
            Path(path).write_text(json.dumps(snapshot, indent=2), encoding="utf-8")


if __name__ == "__main__":
    App().mainloop()
