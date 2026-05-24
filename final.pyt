# -*- coding: utf-8 -*-
import arcpy
import os

class Toolbox:
    def __init__(self):
        """Define the toolbox."""
        self.label = "ParcelReportingToolbox"
        self.alias = "parcel_reporting_toolbox"

        # Register our tool class
        self.tools = [GenerateParcelReportTool]


class GenerateParcelReportTool:
    def __init__(self):
        """Define the tool."""
        self.label = "Generate Parcel Report"
        self.description = "Analyzes parcel and building data, then generates a summary report table."

    def getParameterInfo(self):
        """Define the tool parameters."""
        
        # 1. Parcel Layer Parameter (Polygon)
        in_parcel = arcpy.Parameter(
            displayName="Parcel Layer",
            name="in_parcel_layer",
            datatype="GPFeatureLayer",
            parameterType="Required",
            direction="Input"
        )
        
        # 2. Building Layer Parameter (Polygon)
        in_building = arcpy.Parameter(
            displayName="Building Layer",
            name="in_building_layer",
            datatype="GPFeatureLayer",
            parameterType="Required",
            direction="Input"
        )
        
        # 3. Output Table Parameter
        out_table = arcpy.Parameter(
            displayName="Output Table",
            name="out_table",
            datatype="DETable",
            parameterType="Required",
            direction="Output"
        )
        
        # 4. Bonus Parameter: Action Type (Overwrite or Append)
        existing_table_action = arcpy.Parameter(
            displayName="Existing Table Action",
            name="existing_table_action",
            datatype="GPString",
            parameterType="Required",
            direction="Input"
        )
        existing_table_action.filter.type = "ValueList"
        existing_table_action.filter.list = ["Overwrite", "Append"]
        existing_table_action.value = "Overwrite"
        
        parameter_list = [in_parcel, in_building, out_table, existing_table_action]
        return parameter_list

    def updateParameters(self, parameters):
        """Modify parameters before internal validation."""
        return
        
    def updateMessages(self, parameters):
        """Modify messages created by internal validation."""
        in_parcel = parameters[0]
        in_building = parameters[1]
        
        # التأكد من أن الطبقات المدخلة عبارة عن مضلعات (Polygons)
        if in_parcel and in_parcel.value:
            desc_parcel = arcpy.Describe(in_parcel.value)
            if desc_parcel.shapeType != "Polygon":
                in_parcel.setErrorMessage("Invalid shape type. The Parcel Layer must be a Polygon layer.")
                
        if in_building and in_building.value:
            desc_building = arcpy.Describe(in_building.value)
            if desc_building.shapeType != "Polygon":
                in_building.setErrorMessage("Invalid shape type. The Building Layer must be a Polygon layer.")
                
        return
        
    def execute(self, parameters, messages):
        """The source code of the tool."""
        arcpy.AddMessage("Starting Parcel Report Generation...")
        
        # جلب قيم المتغيرات من الواجهة
        parcel_layer = parameters[0].valueAsText
        building_layer = parameters[1].valueAsText
        out_table_path = parameters[2].valueAsText
        table_action = parameters[3].valueAsText
        
        # تحديد أسماء الحقول الحقيقية والمطابقة لقطات الشاشة تماماً
        ORIGINAL_PARCEL_NAME_FIELD = "parcel_number" 
        ORIGINAL_BUILDING_CODE_FIELD = "code"       
        ORIGINAL_PRIMARY_USE_FIELD = "primary_use"  
        
        # استخراج مسار المجلد واسم الجدول
        output_workspace = os.path.dirname(out_table_path)
        table_name = os.path.basename(out_table_path)
        
        # التحقق من وجود الجدول وإدارته حسب اختيار المستخدم
        table_exists = arcpy.Exists(out_table_path)
        
        if table_exists and table_action == "Overwrite":
            arcpy.AddWarning("Output table already exists. Overwriting as requested...")
            arcpy.management.Delete(out_table_path)
            table_exists = False
            
        if not table_exists:
            arcpy.AddMessage("Creating output table: {0}".format(table_name))
            arcpy.management.CreateTable(output_workspace, table_name)
            
            # إضافة الحقول المطلوبة للتأسيس كما هو محدد بالتاسك
            arcpy.AddMessage("Adding report fields...")
            arcpy.management.AddField(out_table_path, "Parcel_Name", "TEXT", field_length=100)
            arcpy.management.AddField(out_table_path, "Inside_Buildings_Code", "TEXT", field_length=255)
            arcpy.management.AddField(out_table_path, "Total_Residential_Area", "DOUBLE")
            arcpy.management.AddField(out_table_path, "Total_Commercial_Area", "DOUBLE")
        else:
            arcpy.AddMessage("Output table exists. Appending new records...")
        
        # قراءة بيانات المباني بالكامل وحفظ هندستها في الذاكرة لتسريع المعالجة
        buildings_data = []
        building_fields = ["SHAPE@", ORIGINAL_BUILDING_CODE_FIELD, ORIGINAL_PRIMARY_USE_FIELD]
        
        arcpy.AddMessage("Reading building geometries and attributes...")
        with arcpy.da.SearchCursor(building_layer, building_fields) as b_cursor:
            for b_row in b_cursor:
                buildings_data.append({
                    "geometry": b_row[0],
                    "code": b_row[1],
                    "use": b_row[2]
                })
        
        # الحقول الخاصة بجدول المخرجات والطبقة الأصلية للأراضي
        insert_fields = ["Parcel_Name", "Inside_Buildings_Code", "Total_Residential_Area", "Total_Commercial_Area"]
        parcel_fields = ["SHAPE@", ORIGINAL_PARCEL_NAME_FIELD]
        
        arcpy.AddMessage("Analyzing spatial relationships and calculating areas...")
        with arcpy.da.InsertCursor(out_table_path, insert_fields) as i_cursor:
            with arcpy.da.SearchCursor(parcel_layer, parcel_fields) as p_cursor:
                for p_row in p_cursor:
                    parcel_geom = p_row[0]
                    parcel_name = p_row[1]
                    
                    building_codes = []
                    total_res_area = 0.0
                    total_com_area = 0.0
                    
                    # القيام بالتحليل المكاني وحساب المساحات لكل قطعة أرض
                    for building in buildings_data:
                        b_geom = building["geometry"]
                        
                        # قياس الاحتواء الهندسي المكاني (Polygon Contains Polygon)
                        if parcel_geom.contains(b_geom):
                            if building["code"]:
                                building_codes.append(str(building["code"]))
                            
                            # حساب مساحة المبنى بالمتر المربع حسب نوع استخدامه
                            if building["use"] == "resd":
                                total_res_area += b_geom.area
                            elif building["use"] == "com":
                                total_com_area += b_geom.area
                    
                    # تحويل الأكواد لنص مفصول بفاصلة
                    codes_str = ", ".join(building_codes)
                    
                    # إدراج السجل النهائي الخاص بقطعة الأرض في الجدول المخرجات
                    i_cursor.insertRow([str(parcel_name), codes_str, total_res_area, total_com_area])
        
        arcpy.AddMessage("Parcel Report Generated Successfully!")
        return