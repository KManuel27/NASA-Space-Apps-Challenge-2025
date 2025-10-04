"""
Provides energy impact calculation function for a single estimated value.

Based on assumptions:
- Average diameter from min and max diameters
- Density of 3000 kg/m^3 (typical for rocky asteroids) - also used as an example in NASA Space Challenge Page
"""

import math


def energy_impact(mass_kg: float, velocity_km_s: float) -> float:
    """Computes kinetic energy in megatons of TNT for a given mass (kg) and velocity (km/s)."""
    # KE = 1/2 m v^2
    velocity_m_s = velocity_km_s * 1000
    ke_joules = 0.5 * mass_kg * (velocity_m_s ** 2)

    # Convert joules to megatons of TNT
    joules_per_megaton_tnt = 4.184e15
    ke_megatons = ke_joules / joules_per_megaton_tnt
    return ke_megatons


def energy_impact_estimation(
    max_diameter_km: float, min_diameter_km: float, velocity_km_s: float, density_kg_m3: float = 3000
) -> float:
    """Estimates a single kinetic energy value in megatons of TNT based on the average diameter."""

    avg_diameter_km = (min_diameter_km + max_diameter_km) / 2
    avg_radius_m = (avg_diameter_km * 1000) / 2

    # Calculate volume from the average radius
    volume_m3 = (4/3) * math.pi * (avg_radius_m ** 3)

    # Calculate mass from the volume
    mass_kg = density_kg_m3 * volume_m3

    # Return a single kinetic energy value
    return energy_impact(mass_kg, velocity_km_s)


if __name__ == "__main__":
    # Example: (2006 SS134)
    max_diameter_km = 0.3006353038
    min_diameter_km = 0.1344481952
    velocity_km_s = 18.9653044315

    # Get the single estimated KE value
    ke_estimate = energy_impact_estimation(max_diameter_km, min_diameter_km, velocity_km_s)

    print(f"Estimated kinetic energy: {ke_estimate:.2f} megatons of TNT")
