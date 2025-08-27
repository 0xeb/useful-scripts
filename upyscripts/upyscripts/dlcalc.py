#!/usr/bin/env python
"""
Daylight calculator - Calculate and visualize daylight hours and sunset times for any location.
"""

import datetime
import argparse
import json
import sys
import time
from astral.sun import sun
from astral import LocationInfo
from astral.geocoder import database, lookup, all_locations
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import numpy as np
import pandas as pd
import pytz
import requests
from tzlocal import get_localzone


def time_to_minutes_from_midnight(t):
    """Convert time to minutes from midnight for easier plotting."""
    return t.hour * 60 + t.minute + t.second / 60


def geocode_location(location_str, enable_geocoding=True):
    """
    Try to geocode a location string using Nominatim (OpenStreetMap).
    Returns tuple: (lat, lon, display_name) or (None, None, None) if failed.
    """
    if not enable_geocoding:
        return None, None, None
    
    try:
        # Use Nominatim API with proper User-Agent
        headers = {'User-Agent': 'upy.dlcalc/1.0 (https://github.com/upyscripts)'}
        params = {
            'q': location_str,
            'format': 'json',
            'limit': 1,
            'addressdetails': 1
        }
        
        response = requests.get(
            'https://nominatim.openstreetmap.org/search',
            params=params,
            headers=headers,
            timeout=5
        )
        
        if response.status_code == 200 and response.json():
            data = response.json()[0]
            lat = float(data['lat'])
            lon = float(data['lon'])
            display_name = data.get('display_name', location_str)
            
            # Be respectful to the free API
            time.sleep(1)
            
            return lat, lon, display_name
    except Exception as e:
        # Silently fail and fall back to manual entry
        pass
    
    return None, None, None


def parse_location(location_str, enable_geocoding=True):
    """
    Parse location string in various formats:
    - "City, State, Country" (e.g., "New York, NY, USA")
    - "City, Country" (e.g., "London, UK")
    - "City" (will try to lookup in Astral database)
    
    Will attempt geocoding if not found in database and geocoding is enabled.
    
    Returns tuple: (LocationInfo or dict, needs_coordinates, geocoded_display_name)
    """
    parts = [part.strip() for part in location_str.split(',')]
    
    # Try to lookup in Astral's built-in database first
    try:
        db_location = lookup(parts[0], database())
        return LocationInfo(
            name=db_location.name,
            region=db_location.region,
            timezone=db_location.timezone,
            latitude=db_location.latitude,
            longitude=db_location.longitude
        ), False, None
    except KeyError:
        pass
    
    # Try geocoding if enabled
    lat, lon, display_name = geocode_location(location_str, enable_geocoding)
    
    if lat is not None and lon is not None:
        # Successfully geocoded
        if len(parts) == 1:
            name = parts[0]
            region = "geocoded"
        elif len(parts) == 2:
            name = parts[0]
            region = parts[1]
        else:
            name = parts[0]
            region = f"{parts[1]}, {parts[2]}" if len(parts) > 2 else parts[1]
        
        return {
            'name': name,
            'region': region,
            'latitude': lat,
            'longitude': lon,
            'geocoded': True,
            'display_name': display_name
        }, False, display_name
    
    # If not in database and geocoding failed, return location info without coordinates
    if len(parts) == 1:
        name = parts[0]
        region = ""
    elif len(parts) == 2:
        name = parts[0]
        region = parts[1]
    else:
        name = parts[0]
        region = f"{parts[1]}, {parts[2]}" if len(parts) > 2 else parts[1]
    
    # Return a tuple indicating location needs coordinates
    return {'name': name, 'region': region}, True, None


def daylight_data(location, start_date, end_date, step_days=14):
    """Calculate daylight hours and sunset times for the given date range."""
    date = start_date
    daylight_lengths = []
    sunrise_times = []
    sunset_times = []
    dates = []
    
    # Get timezone for the location
    try:
        if hasattr(location, 'timezone') and location.timezone:
            # Location has a timezone (from database or user-specified)
            tz = pytz.timezone(location.timezone)
        else:
            # No timezone specified, use system's local timezone
            tz = get_localzone()
    except:
        tz = get_localzone()
    
    while date <= end_date:
        try:
            s = sun(location.observer, date=date, tzinfo=tz)
            daylight_length = (s['sunset'] - s['sunrise']).seconds / 3600
            daylight_lengths.append(daylight_length)
            # Now times are in local timezone
            sunrise_times.append(time_to_minutes_from_midnight(s['sunrise'].time()))
            sunset_times.append(time_to_minutes_from_midnight(s['sunset'].time()))
            dates.append(date)
        except Exception as e:
            # Handle edge cases like polar night/day
            print(f"Warning: Could not calculate sun times for {date}: {e}", file=sys.stderr)
            daylight_lengths.append(0)
            sunrise_times.append(0)
            sunset_times.append(0)
            dates.append(date)
        
        date += datetime.timedelta(days=step_days)
    
    return dates, daylight_lengths, sunrise_times, sunset_times


def create_plot(dates, daylight_lengths, sunrise_times, sunset_times, location_name, output_file=None):
    """Create and optionally save the daylight visualization plot."""
    # Create DataFrame for monthly averages
    data = pd.DataFrame({
        'date': pd.to_datetime(dates),
        'daylight_length': daylight_lengths,
        'sunrise_time': sunrise_times,
        'sunset_time': sunset_times
    })
    data['month'] = data['date'].dt.month
    monthly_data = data.groupby('month').mean()
    
    # Convert average times back to readable format
    monthly_data['sunrise_time_fmt'] = monthly_data['sunrise_time'].apply(
        lambda x: f"{int(x // 60):02d}:{int(x % 60):02d}"
    )
    monthly_data['sunset_time_fmt'] = monthly_data['sunset_time'].apply(
        lambda x: f"{int(x // 60):02d}:{int(x % 60):02d}"
    )
    
    # Create the plot
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 10))
    
    # Set window title and figure super title
    year_range = f"{dates[0].year}" if dates[0].year == dates[-1].year else f"{dates[0].year}-{dates[-1].year}"
    fig.suptitle(f'Solar Analysis for {location_name} ({year_range})', fontsize=16, fontweight='bold')
    
    # Try to set window title (may not work in all backends)
    try:
        fig.canvas.manager.set_window_title(f'Daylight Calculator - {location_name}')
    except:
        pass  # Some backends don't support window titles
    
    # Plot sunset times
    ax1.plot(dates, sunset_times, marker='o', color='orange', label='Sunset Time', linewidth=2)
    ax1.set(xlabel='Date', ylabel='Time of Day', title=f'Sunset Times in {location_name}')
    ax1.xaxis.set_major_formatter(mdates.DateFormatter('%b'))
    ax1.xaxis.set_major_locator(mdates.MonthLocator())
    ax1.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, pos: f'{int(x // 60):02d}:{int(x % 60):02d}'))
    ax1.grid(True, alpha=0.3)
    ax1.legend(loc='upper right')
    
    # Plot daylight hours
    ax2.bar(dates, daylight_lengths, width=10, color='gold', alpha=0.7, label='Daylight Hours')
    ax2.set(xlabel='Date', ylabel='Hours', title=f'Daylight Hours in {location_name}')
    ax2.xaxis.set_major_formatter(mdates.DateFormatter('%b'))
    ax2.xaxis.set_major_locator(mdates.MonthLocator())
    ax2.grid(True, alpha=0.3)
    ax2.legend(loc='upper right')
    
    # Add sunrise times as secondary plot
    ax1.plot(dates, sunrise_times, marker='s', color='skyblue', label='Sunrise Time', linewidth=2)
    ax1.legend(loc='upper right')
    
    plt.xticks(rotation=45)
    plt.tight_layout(rect=[0, 0, 1, 0.96])  # Leave space for suptitle
    
    # Add monthly averages table
    table_data = list(zip(
        monthly_data.index.map(lambda x: datetime.date(1900, x, 1).strftime('%b')),
        np.round(monthly_data['daylight_length'], 1),
        monthly_data['sunrise_time_fmt'],
        monthly_data['sunset_time_fmt']
    ))
    
    table = plt.table(
        cellText=table_data,
        colLabels=['Month', 'Avg Daylight (hrs)', 'Avg Sunrise', 'Avg Sunset'],
        loc='right',
        cellLoc='center',
        bbox=[1.12, 0.1, 0.45, 0.8]  # Increased width from 0.35 to 0.45
    )
    
    # Manually set column widths for better spacing
    for i, width in enumerate([0.15, 0.35, 0.25, 0.25]):
        for key, cell in table.get_celld().items():
            if key[1] == i:
                cell.set_width(width)
    
    table.auto_set_font_size(False)
    table.set_fontsize(10)
    table.scale(1.2, 1.5)
    
    plt.subplots_adjust(right=0.65)
    
    if output_file:
        plt.savefig(output_file, dpi=150, bbox_inches='tight')
        print(f"Plot saved to {output_file}")
    else:
        plt.show()


def print_table(dates, daylight_lengths, sunrise_times, sunset_times, location_name):
    """Print daylight data as a formatted table."""
    # Create DataFrame for display
    data = pd.DataFrame({
        'Date': dates,
        'Daylight (hrs)': [f"{dl:.1f}" for dl in daylight_lengths],
        'Sunrise': [f"{int(st // 60):02d}:{int(st % 60):02d}" for st in sunrise_times],
        'Sunset': [f"{int(st // 60):02d}:{int(st % 60):02d}" for st in sunset_times]
    })
    
    print(f"\nDaylight Hours and Sun Times for {location_name}")
    print("=" * 60)
    print(data.to_string(index=False))
    
    # Calculate and print monthly averages
    data['date'] = pd.to_datetime(dates)
    data['month'] = data['date'].dt.month
    data['Daylight (hrs)'] = daylight_lengths
    data['Sunrise (min)'] = sunrise_times
    data['Sunset (min)'] = sunset_times
    
    monthly_avg = data.groupby('month').agg({
        'Daylight (hrs)': 'mean',
        'Sunrise (min)': 'mean',
        'Sunset (min)': 'mean'
    })
    
    print("\n\nMonthly Averages")
    print("=" * 70)
    print(f"{'Month':<12} {'Daylight':<12} {'Avg Sunrise':<15} {'Avg Sunset':<15}")
    print("-" * 70)
    
    for month in monthly_avg.index:
        month_name = datetime.date(1900, month, 1).strftime('%B')
        avg_daylight = monthly_avg.loc[month, 'Daylight (hrs)']
        avg_sunrise = monthly_avg.loc[month, 'Sunrise (min)']
        avg_sunset = monthly_avg.loc[month, 'Sunset (min)']
        
        # Convert minutes to time format
        sunrise_str = f"{int(avg_sunrise // 60):02d}:{int(avg_sunrise % 60):02d}"
        sunset_str = f"{int(avg_sunset // 60):02d}:{int(avg_sunset % 60):02d}"
        
        print(f"{month_name:<12} {avg_daylight:>5.1f} hours  {sunrise_str:<15} {sunset_str:<15}")


def output_json(dates, daylight_lengths, sunrise_times, sunset_times, location_name):
    """Output daylight data as JSON."""
    data = []
    for i, date in enumerate(dates):
        data.append({
            'date': date.isoformat(),
            'daylight_hours': round(daylight_lengths[i], 2),
            'sunrise': f"{int(sunrise_times[i] // 60):02d}:{int(sunrise_times[i] % 60):02d}",
            'sunset': f"{int(sunset_times[i] // 60):02d}:{int(sunset_times[i] % 60):02d}"
        })
    
    output = {
        'location': location_name,
        'data': data
    }
    
    print(json.dumps(output, indent=2))


def main():
    parser = argparse.ArgumentParser(
        description='Calculate and visualize daylight hours and sunset times for any location.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  upy.dlcalc --location "New York"                    # Built-in location
  upy.dlcalc --location "Bellevue, Washington"        # Geocoded location
  upy.dlcalc --location "London, UK" --gui            # Show interactive plot
  upy.dlcalc --location "Tokyo" --year 2024           # Show 2024 data
  upy.dlcalc --location "My City" --lat 40.71 --lon -74.00  # Manual coords
  upy.dlcalc --location "Paris" --format json         # Output as JSON
  upy.dlcalc --location "Berlin" --offline            # No geocoding
  upy.dlcalc --list-locations                         # List built-in cities
        """
    )
    
    # Location arguments
    parser.add_argument(
        '--location', '-l',
        type=str,
        default="New York, USA",
        help='Location as "City, State, Country" or "City, Country" or just "City"'
    )
    parser.add_argument(
        '--lat', '--latitude',
        type=float,
        help='Latitude (required if location not in database)'
    )
    parser.add_argument(
        '--lon', '--longitude',
        type=float,
        help='Longitude (required if location not in database)'
    )
    parser.add_argument(
        '--timezone', '-tz',
        type=str,
        help='Timezone (e.g., "America/New_York", "Europe/London")'
    )
    
    # Date range arguments
    parser.add_argument(
        '--year', '-y',
        type=int,
        default=datetime.datetime.now().year,
        help='Year to calculate for (default: current year)'
    )
    parser.add_argument(
        '--start-date',
        type=lambda s: datetime.datetime.strptime(s, '%Y-%m-%d').date(),
        help='Start date (YYYY-MM-DD format)'
    )
    parser.add_argument(
        '--end-date',
        type=lambda s: datetime.datetime.strptime(s, '%Y-%m-%d').date(),
        help='End date (YYYY-MM-DD format)'
    )
    parser.add_argument(
        '--step-days',
        type=int,
        default=7,
        help='Days between calculations (default: 7)'
    )
    
    # Output arguments
    parser.add_argument(
        '--format', '-f',
        choices=['plot', 'table', 'json'],
        default='table',
        help='Output format (default: table)'
    )
    parser.add_argument(
        '--gui', '-g',
        action='store_true',
        help='Show interactive GUI plot (shortcut for --format plot)'
    )
    parser.add_argument(
        '--output-file', '-o',
        type=str,
        help='Save plot to file (PNG, JPG, PDF, etc.)'
    )
    parser.add_argument(
        '--no-plot',
        action='store_true',
        help='Disable plot display (useful with --output-file)'
    )
    parser.add_argument(
        '--list-locations',
        action='store_true',
        help='List all available locations in the database'
    )
    parser.add_argument(
        '--offline',
        action='store_true',
        help='Disable online geocoding (only use built-in database)'
    )
    
    args = parser.parse_args()
    
    # Handle list locations
    if args.list_locations:
        print("Available locations in database:")
        print("-" * 60)
        locations = all_locations(database())
        # Sort by name and remove duplicates
        seen = set()
        for location in sorted(locations, key=lambda x: x.name):
            if location.name not in seen:
                print(f"{location.name:30s} {location.region:25s}")
                seen.add(location.name)
        return
    
    # Parse location
    try:
        location_data, needs_coords, geocoded_name = parse_location(
            args.location, 
            enable_geocoding=not args.offline
        )
        
        if needs_coords:
            # Location not in database and geocoding failed/disabled
            if args.lat is None or args.lon is None:
                print(f"Error: Location '{args.location}' not found.")
                if args.offline:
                    print("\nGeocoding is disabled (--offline flag).")
                else:
                    print("\nCould not geocode this location (may not exist or API issue).")
                print("\nYou must provide coordinates manually:")
                print("  --lat <latitude> --lon <longitude>")
                print("\nOr use --list-locations to see available built-in locations")
                print("\nExample:")
                print(f"  upy.dlcalc --location \"{args.location}\" --lat 40.7128 --lon -74.0060")
                return 1
            
            # Create LocationInfo with provided coordinates
            # Use system timezone unless explicitly provided
            if args.timezone:
                tz_to_use = args.timezone
            else:
                # Use system's local timezone
                local_tz = get_localzone()
                tz_to_use = str(local_tz)
            
            location = LocationInfo(
                name=location_data['name'],
                region=location_data['region'],
                latitude=args.lat,
                longitude=args.lon,
                timezone=tz_to_use
            )
        else:
            # Location found in database or geocoded
            if isinstance(location_data, dict) and location_data.get('geocoded'):
                # Create LocationInfo from geocoded data
                # Use system timezone unless explicitly provided
                if args.timezone:
                    tz_to_use = args.timezone
                else:
                    # Use system's local timezone
                    local_tz = get_localzone()
                    tz_to_use = str(local_tz)
                
                location = LocationInfo(
                    name=location_data['name'],
                    region=location_data['region'],
                    latitude=location_data['latitude'],
                    longitude=location_data['longitude'],
                    timezone=tz_to_use
                )
                if geocoded_name:
                    print(f"Geocoded: {geocoded_name}")
                    print(f"Coordinates: {location_data['latitude']:.4f}, {location_data['longitude']:.4f}")
                    print()
            else:
                # Location from Astral database
                location = location_data
            
            # Override coordinates if provided
            if args.lat is not None and args.lon is not None:
                location.latitude = args.lat
                location.longitude = args.lon
            
            # Set timezone if provided
            if args.timezone:
                location.timezone = args.timezone
            
    except Exception as e:
        print(f"Error parsing location: {e}", file=sys.stderr)
        return 1
    
    # Set date range
    if args.start_date and args.end_date:
        start_date = args.start_date
        end_date = args.end_date
    else:
        start_date = datetime.date(args.year, 1, 1)
        end_date = datetime.date(args.year, 12, 31)
    
    # Calculate daylight data
    try:
        dates, daylight_lengths, sunrise_times, sunset_times = daylight_data(
            location, start_date, end_date, args.step_days
        )
    except Exception as e:
        print(f"Error calculating daylight data: {e}", file=sys.stderr)
        return 1
    
    # Format location name for display
    location_name = f"{location.name}"
    if location.region:
        location_name += f", {location.region}"
    
    # Handle --gui flag (overrides format)
    if args.gui:
        output_format = 'plot'
    else:
        output_format = args.format
    
    # Output results based on format
    if output_format == 'json':
        output_json(dates, daylight_lengths, sunrise_times, sunset_times, location_name)
    elif output_format == 'table':
        print_table(dates, daylight_lengths, sunrise_times, sunset_times, location_name)
    elif output_format == 'plot':
        if args.no_plot and not args.output_file:
            print("Warning: --no-plot specified without --output-file, no output generated")
        else:
            create_plot(dates, daylight_lengths, sunrise_times, sunset_times, 
                       location_name, args.output_file)
    
    return 0


if __name__ == "__main__":
    sys.exit(main())