from nautobot.extras.jobs import Job, FileVar, StringVar, BooleanVar, ObjectVar
from nautobot.dcim.models import Device, DeviceType, Site, Platform, Manufacturer, Interface
from nautobot.extras.models import Status, DeviceRole
from django.core.exceptions import ValidationError
import pandas as pd
import io
import logging

logger = logging.getLogger(__name__)

class SpreadsheetImportJob(Job):
    """
    Job to import devices and interfaces from a spreadsheet (Excel or CSV).
    """
    
    class Meta:
        name = "Import Devices and Interfaces from Spreadsheet"
        description = "Import device names and interfaces from uploaded Excel/CSV file"
        has_sensitive_variables = False

    # File upload
    spreadsheet_file = FileVar(
        required=True,
        description="Upload Excel (.xlsx) or CSV file containing device and interface data"
    )
    
    # Column mapping
    device_name_column = StringVar(
        required=True,
        default="Device Name",
        description="Column name containing device names"
    )
    
    interface_name_column = StringVar(
        required=True,
        default="Interface",
        description="Column name containing interface names"
    )
    
    # Optional columns
    device_type_column = StringVar(
        required=False,
        description="Optional: Column name containing device types"
    )
    
    site_column = StringVar(
        required=False,
        description="Optional: Column name containing site names"
    )
    
    # Default values for required fields
    default_device_type = ObjectVar(
        model=DeviceType,
        required=True,
        description="Default device type for devices without specific type"
    )
    
    default_device_role = ObjectVar(
        model=DeviceRole,
        required=True,
        description="Default device role for all devices"
    )
    
    default_site = ObjectVar(
        model=Site,
        required=True,
        description="Default site for devices without specific site"
    )
    
    default_platform = ObjectVar(
        model=Platform,
        required=False,
        description="Optional: Default platform for all devices"
    )
    
    # Processing options
    create_missing_devices = BooleanVar(
        default=True,
        description="Create devices that don't exist in Nautobot"
    )
    
    create_missing_interfaces = BooleanVar(
        default=True,
        description="Create interfaces that don't exist on devices"
    )
    
    update_existing = BooleanVar(
        default=False,
        description="Update existing interfaces (otherwise skip)"
    )
    
    dry_run = BooleanVar(
        default=True,
        description="Dry run - don't actually create/update objects"
    )

    def run(self):
        """Main job execution method."""
        
        try:
            # Read the spreadsheet
            df = self._read_spreadsheet()
            
            if df is None or df.empty:
                return "ERROR: Could not read spreadsheet or file is empty"
            
            self.logger.info(f"Successfully read spreadsheet with {len(df)} rows")
            
            # Validate required columns exist
            validation_result = self._validate_columns(df)
            if validation_result:
                return validation_result
            
            # Clean and prepare data
            df_clean = self._clean_data(df)
            
            # Process the data
            results = self._process_data(df_clean)
            
            return self._format_results(results)
            
        except Exception as e:
            error_msg = f"Error processing spreadsheet: {str(e)}"
            self.logger.error(error_msg)
            return f"ERROR: {error_msg}"
    
    def _read_spreadsheet(self):
        """Read the uploaded spreadsheet file."""
        
        try:
            # Get file content
            file_content = self.spreadsheet_file.read()
            
            # Determine file type and read accordingly
            filename = self.spreadsheet_file.name.lower()
            
            if filename.endswith('.csv'):
                # Read CSV
                df = pd.read_csv(io.BytesIO(file_content))
                self.logger.info("Successfully read CSV file")
            elif filename.endswith(('.xlsx', '.xls')):
                # Read Excel
                df = pd.read_excel(io.BytesIO(file_content))
                self.logger.info("Successfully read Excel file")
            else:
                raise ValueError("Unsupported file type. Please upload CSV or Excel file.")
            
            return df
            
        except Exception as e:
            self.logger.error(f"Error reading file: {str(e)}")
            raise
    
    def _validate_columns(self, df):
        """Validate that required columns exist in the spreadsheet."""
        
        missing_columns = []
        
        if self.device_name_column not in df.columns:
            missing_columns.append(self.device_name_column)
        
        if self.interface_name_column not in df.columns:
            missing_columns.append(self.interface_name_column)
        
        if missing_columns:
            available_columns = ", ".join(df.columns.tolist())
            return (f"ERROR: Missing required columns: {', '.join(missing_columns)}\n"
                   f"Available columns: {available_columns}")
        
        return None
    
    def _clean_data(self, df):
        """Clean and prepare the data for processing."""
        
        # Create a copy for processing
        df_clean = df.copy()
        
        # Remove rows where device name or interface name is empty
        df_clean = df_clean.dropna(subset=[self.device_name_column, self.interface_name_column])
        
        # Strip whitespace from string columns
        string_columns = [self.device_name_column, self.interface_name_column]
        
        if self.device_type_column and self.device_type_column in df_clean.columns:
            string_columns.append(self.device_type_column)
        
        if self.site_column and self.site_column in df_clean.columns:
            string_columns.append(self.site_column)
        
        for col in string_columns:
            if col in df_clean.columns:
                df_clean[col] = df_clean[col].astype(str).str.strip()
        
        self.logger.info(f"Cleaned data: {len(df_clean)} rows after removing empty entries")
        
        return df_clean
    
    def _process_data(self, df):
        """Process the cleaned data and create/update objects."""
        
        results = {
            'devices_created': 0,
            'devices_found': 0,
            'interfaces_created': 0,
            'interfaces_updated': 0,
            'interfaces_skipped': 0,
            'errors': [],
            'summary': []
        }
        
        # Get active status
        active_status = Status.objects.get(name="Active")
        
        # Group by device to process efficiently
        device_groups = df.groupby(self.device_name_column)
        
        for device_name, device_data in device_groups:
            try:
                # Process device
                device, device_created = self._process_device(device_name, device_data.iloc[0], active_status)
                
                if device_created:
                    results['devices_created'] += 1
                    results['summary'].append(f"Created device: {device_name}")
                else:
                    results['devices_found'] += 1
                
                if device:
                    # Process interfaces for this device
                    interface_results = self._process_interfaces(device, device_data)
                    results['interfaces_created'] += interface_results['created']
                    results['interfaces_updated'] += interface_results['updated']
                    results['interfaces_skipped'] += interface_results['skipped']
                    results['summary'].extend(interface_results['messages'])
                
            except Exception as e:
                error_msg = f"Error processing device {device_name}: {str(e)}"
                results['errors'].append(error_msg)
                self.logger.error(error_msg)
        
        return results
    
    def _process_device(self, device_name, device_row, active_status):
        """Process a single device."""
        
        device_created = False
        
        try:
            # Try to find existing device
            device = Device.objects.get(name=device_name)
            self.logger.info(f"Found existing device: {device_name}")
            
        except Device.DoesNotExist:
            if not self.create_missing_devices:
                self.logger.warning(f"Device {device_name} not found and creation disabled")
                return None, False
            
            # Create new device
            if self.dry_run:
                self.logger.info(f"DRY RUN: Would create device {device_name}")
                return None, True
            
            # Determine device type
            device_type = self.default_device_type
            if (self.device_type_column and 
                self.device_type_column in device_row and 
                pd.notna(device_row[self.device_type_column])):
                try:
                    device_type = DeviceType.objects.get(model=device_row[self.device_type_column])
                except DeviceType.DoesNotExist:
                    self.logger.warning(f"Device type {device_row[self.device_type_column]} not found, using default")
            
            # Determine site
            site = self.default_site
            if (self.site_column and 
                self.site_column in device_row and 
                pd.notna(device_row[self.site_column])):
                try:
                    site = Site.objects.get(name=device_row[self.site_column])
                except Site.DoesNotExist:
                    self.logger.warning(f"Site {device_row[self.site_column]} not found, using default")
            
            # Create device
            device = Device(
                name=device_name,
                device_type=device_type,
                device_role=self.default_device_role,
                site=site,
                status=active_status
            )
            
            if self.default_platform:
                device.platform = self.default_platform
            
            device.validated_save()
            device_created = True
            self.logger.info(f"Created device: {device_name}")
        
        return device, device_created
    
    def _process_interfaces(self, device, interfaces_data):
        """Process interfaces for a device."""
        
        results = {
            'created': 0,
            'updated': 0,
            'skipped': 0,
            'messages': []
        }
        
        for _, row in interfaces_data.iterrows():
            interface_name = row[self.interface_name_column]
            
            try:
                # Try to find existing interface
                interface = Interface.objects.get(device=device, name=interface_name)
                
                if self.update_existing:
                    if not self.dry_run:
                        # Update interface if needed
                        interface.save()
                    results['updated'] += 1
                    results['messages'].append(f"  Updated interface: {interface_name}")
                else:
                    results['skipped'] += 1
                    results['messages'].append(f"  Skipped existing interface: {interface_name}")
                
            except Interface.DoesNotExist:
                if not self.create_missing_interfaces:
                    results['skipped'] += 1
                    continue
                
                if self.dry_run:
                    results['created'] += 1
                    results['messages'].append(f"  DRY RUN: Would create interface: {interface_name}")
                    continue
                
                # Create new interface
                interface = Interface(
                    device=device,
                    name=interface_name,
                    type="other"  # Default type, you might want to make this configurable
                )
                
                interface.validated_save()
                results['created'] += 1
                results['messages'].append(f"  Created interface: {interface_name}")
        
        return results
    
    def _format_results(self, results):
        """Format the results for display."""
        
        output = []
        output.append("=" * 80)
        output.append("SPREADSHEET IMPORT RESULTS")
        output.append("=" * 80)
        
        if self.dry_run:
            output.append("*** DRY RUN MODE - NO CHANGES MADE ***")
            output.append("")
        
        # Summary statistics
        output.append("SUMMARY:")
        output.append(f"  Devices created: {results['devices_created']}")
        output.append(f"  Devices found: {results['devices_found']}")
        output.append(f"  Interfaces created: {results['interfaces_created']}")
        output.append(f"  Interfaces updated: {results['interfaces_updated']}")
        output.append(f"  Interfaces skipped: {results['interfaces_skipped']}")
        output.append(f"  Errors: {len(results['errors'])}")
        output.append("")
        
        # Detailed messages
        if results['summary']:
            output.append("DETAILED RESULTS:")
            output.extend(results['summary'])
            output.append("")
        
        # Errors
        if results['errors']:
            output.append("ERRORS:")
            output.extend(results['errors'])
            output.append("")
        
        output.append("=" * 80)
        
        return "\n".join(output)

# Register the job
jobs = [SpreadsheetImportJob]
