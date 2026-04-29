import datetime
import io
import textwrap
from decimal import Decimal
from xml.sax.saxutils import escape

from django.utils.text import slugify

from .reporting import REPORT_SECTION_DETAILS


def build_report_export_payload(section, context):
    title = REPORT_SECTION_DETAILS[section]["title"]
    heading = REPORT_SECTION_DETAILS[section]["heading"]
    generated_at = context["report_generated_at"]
    generated_by = context["report_generated_by"]
    filters_text = context["report_active_filters_text"]
    export_sources = context["report_export_sources"]
    report_summary = context["report_summary"]
    depreciation_totals = context["depreciation_totals"]

    if section == "inventory-report":
        columns = [
            "Asset ID",
            "Name",
            "Category",
            "Department",
            "Location",
            "Status",
            "Condition",
            "Purchase Date",
            "Purchase Cost",
        ]
        rows = [
            [
                asset.asset_id,
                asset.name,
                asset.category.name,
                asset.current_location.department.name,
                asset.current_location.short_label,
                asset.get_status_display(),
                asset.get_condition_display(),
                _stringify(asset.purchase_date),
                _stringify(asset.purchase_cost),
            ]
            for asset in export_sources["inventory-report"]
        ]
        summary_pairs = [
            ("Visible assets", report_summary["total_assets"]),
            ("Available assets", report_summary["available_assets"]),
            ("Allocated assets", report_summary["allocated_assets"]),
            ("Maintenance assets", report_summary["maintenance_assets"]),
        ]
    elif section == "dashboard-summary":
        columns = ["Metric", "Value"]
        rows = [
            ["Total Assets", report_summary["total_assets"]],
            ["Available", report_summary["available_assets"]],
            ["Allocated", report_summary["allocated_assets"]],
            ["Under Maintenance", report_summary["maintenance_assets"]],
            ["Disposed", report_summary["disposed_assets"]],
            ["Active Allocations", report_summary["active_allocations"]],
            ["Returned Records", report_summary["returned_allocations"]],
        ]
        summary_pairs = [("Visible scope", context["user_role"])]
    elif section == "assets-by-department":
        columns = ["Department", "Code", "Total Assets"]
        rows = [
            [
                row["current_location__department__name"],
                row["current_location__department__code"],
                row["total_assets"],
            ]
            for row in export_sources["assets-by-department"]
        ]
        summary_pairs = [("Departments listed", len(rows))]
    elif section == "assigned-assets":
        columns = [
            "Asset",
            "Assigned To",
            "Allocation Type",
            "Issued By",
            "Status",
            "Issue Date",
            "Return Date",
            "Purpose",
        ]
        rows = [
            [
                f"{allocation.asset.asset_id} - {allocation.asset.name}",
                _allocation_recipient(allocation),
                allocation.get_allocation_type_display(),
                allocation.allocated_by.username,
                allocation.get_status_display(),
                _stringify(allocation.allocation_date),
                _stringify(allocation.expected_return_date),
                allocation.purpose or "-",
            ]
            for allocation in export_sources["assigned-assets"]
        ]
        summary_pairs = [("Active allocations", report_summary["active_allocations"])]
    elif section == "returned-assets":
        columns = [
            "Asset",
            "Returned From",
            "Allocation Type",
            "Issued By",
            "Issue Date",
            "Expected Return",
            "Actual Return",
            "Condition Out",
            "Condition In",
            "Purpose",
        ]
        rows = [
            [
                f"{allocation.asset.asset_id} - {allocation.asset.name}",
                _allocation_recipient(allocation),
                allocation.get_allocation_type_display(),
                allocation.allocated_by.username,
                _stringify(allocation.allocation_date),
                _stringify(allocation.expected_return_date),
                _stringify(allocation.actual_return_date),
                allocation.get_condition_out_display() if allocation.condition_out else "-",
                allocation.get_condition_in_display() if allocation.condition_in else "-",
                allocation.purpose or "-",
            ]
            for allocation in export_sources["returned-assets"]
        ]
        summary_pairs = [("Returned records", report_summary["returned_allocations"])]
    elif section == "maintenance-history":
        columns = [
            "Asset",
            "Type",
            "Status",
            "Scheduled",
            "Completed",
            "Technician",
            "Reported By",
            "Description",
            "Cost",
            "Resolution",
        ]
        rows = [
            [
                f"{item.asset.asset_id} - {item.asset.name}",
                item.get_maintenance_type_display(),
                item.get_status_display(),
                _stringify(item.scheduled_date),
                _stringify(item.completed_date),
                _stringify(item.technician),
                _stringify(item.reported_by),
                item.description,
                _stringify(item.cost),
                item.resolution_notes or (f"Parts replaced: {item.parts_replaced}" if item.parts_replaced else "-"),
            ]
            for item in export_sources["maintenance-history"]
        ]
        summary_pairs = [("Maintenance records", len(rows))]
    elif section == "asset-movements":
        columns = ["Asset", "From", "To", "Moved By", "Moved At", "Notes"]
        rows = [
            [
                f"{item.asset.asset_id} - {item.asset.name}",
                _stringify(item.from_location),
                _stringify(item.to_location),
                item.moved_by.username,
                _stringify(item.moved_at),
                item.notes or "-",
            ]
            for item in export_sources["asset-movements"]
        ]
        summary_pairs = [("Movement records", len(rows))]
    elif section == "depreciation-summary":
        columns = [
            "Asset",
            "Department",
            "Location",
            "Year",
            "Depreciation",
            "Accumulated",
            "Net Book Value",
        ]
        rows = [
            [
                f"{record.asset.asset_id} - {record.asset.name}",
                record.asset.current_location.department.name,
                record.asset.current_location.short_label,
                record.year,
                _stringify(record.depreciation_amount),
                _stringify(record.accumulated_depreciation),
                _stringify(record.net_book_value),
            ]
            for record in export_sources["depreciation-summary"]
        ]
        summary_pairs = [
            ("Total depreciation", _stringify(depreciation_totals["total_depreciation"] or 0)),
            ("Accumulated depreciation", _stringify(depreciation_totals["total_accumulated"] or 0)),
            ("Book value", _stringify(depreciation_totals["total_book_value"] or 0)),
        ]
    else:
        columns = [
            "Asset",
            "Requested By",
            "Status",
            "Requested At",
            "Use Window",
            "Location",
            "Reviewed By",
            "Decision Date",
            "Issuer Details",
            "Handover Place",
            "Reason",
            "Decision Note",
        ]
        rows = [
            [
                f"{item.asset.asset_id} - {item.asset.name}",
                item.requested_by.username,
                item.get_status_display(),
                _stringify(item.requested_at),
                _request_use_window(item),
                item.usage_location or "-",
                _stringify(item.reviewed_by),
                _stringify(item.reviewed_at),
                item.issue_person_details or "-",
                item.handover_location or "-",
                item.message or "-",
                item.decline_reason or "-",
            ]
            for item in export_sources["request-report"]
        ]
        summary_pairs = [("Request records", len(rows))]

    return {
        "section": section,
        "title": title,
        "heading": heading,
        "columns": columns,
        "rows": rows,
        "summary_pairs": summary_pairs,
        "generated_by": generated_by,
        "generated_at": generated_at,
        "filters_text": filters_text,
    }


def build_export_filename(payload, extension):
    title_slug = slugify(payload["title"]) or "report"
    date_stamp = payload["generated_at"].strftime("%Y%m%d")
    return f"{title_slug}-{date_stamp}.{extension}"


def render_excel_bytes(payload):
    column_count = max(len(payload["columns"]), 1)
    merge_across = max(column_count - 1, 0)
    lines = [
        '<?xml version="1.0"?>',
        '<?mso-application progid="Excel.Sheet"?>',
        '<Workbook xmlns="urn:schemas-microsoft-com:office:spreadsheet"',
        ' xmlns:o="urn:schemas-microsoft-com:office:office"',
        ' xmlns:x="urn:schemas-microsoft-com:office:excel"',
        ' xmlns:ss="urn:schemas-microsoft-com:office:spreadsheet"',
        ' xmlns:html="http://www.w3.org/TR/REC-html40">',
        " <Styles>",
        '  <Style ss:ID="Default" ss:Name="Normal"><Alignment ss:Vertical="Bottom"/><Font ss:FontName="Calibri" ss:Size="11"/><Interior/><NumberFormat/><Protection/></Style>',
        '  <Style ss:ID="Title"><Font ss:FontName="Calibri" ss:Size="16" ss:Bold="1"/></Style>',
        '  <Style ss:ID="Heading"><Font ss:FontName="Calibri" ss:Size="12" ss:Bold="1"/></Style>',
        '  <Style ss:ID="Meta"><Font ss:FontName="Calibri" ss:Size="10"/></Style>',
        '  <Style ss:ID="Header"><Font ss:FontName="Calibri" ss:Bold="1"/><Interior ss:Color="#DCE9EE" ss:Pattern="Solid"/></Style>',
        " </Styles>",
        f' <Worksheet ss:Name="{escape(_truncate_sheet_name(payload["title"]))}">',
        "  <Table>",
        _merged_row(payload["title"], merge_across, "Title"),
        _merged_row(payload["heading"], merge_across, "Heading"),
        _merged_row(f'Generated By: {payload["generated_by"]}', merge_across, "Meta"),
        _merged_row(f'Generated On: {payload["generated_at"].strftime("%b %d, %Y %H:%M")}', merge_across, "Meta"),
        _merged_row(f'Active Filters: {payload["filters_text"]}', merge_across, "Meta"),
    ]

    for label, value in payload["summary_pairs"]:
        lines.append(_merged_row(f"{label}: {value}", merge_across, "Meta"))

    lines.append("   <Row>")
    for column in payload["columns"]:
        lines.append(_cell(column, style="Header"))
    lines.append("   </Row>")

    if payload["rows"]:
        for row in payload["rows"]:
            lines.append("   <Row>")
            for value in row:
                lines.append(_typed_cell(value))
            lines.append("   </Row>")
    else:
        lines.append("   <Row>")
        lines.append(_cell("No rows matched the current filters.", merge_across=merge_across))
        lines.append("   </Row>")

    lines.extend(
        [
            "  </Table>",
            " </Worksheet>",
            "</Workbook>",
        ]
    )
    return "\n".join(lines).encode("utf-8")


def render_pdf_bytes(payload):
    pages = _paginate_pdf_lines(_build_pdf_lines(payload))
    catalog_id = 1
    pages_id = 2
    font_id = 3
    page_object_ids = []
    content_object_ids = []

    next_object_id = 4
    for _ in pages:
        page_object_ids.append(next_object_id)
        content_object_ids.append(next_object_id + 1)
        next_object_id += 2

    rendered_objects = {
        catalog_id: f"<< /Type /Catalog /Pages {pages_id} 0 R >>".encode("ascii"),
        pages_id: f"<< /Type /Pages /Count {len(pages)} /Kids [{' '.join(f'{page_id} 0 R' for page_id in page_object_ids)}] >>".encode("ascii"),
        font_id: b"<< /Type /Font /Subtype /Type1 /BaseFont /Courier >>",
    }

    for index, page_lines in enumerate(pages):
        content_stream = _render_pdf_page_stream(page_lines)
        rendered_objects[page_object_ids[index]] = (
            f"<< /Type /Page /Parent {pages_id} 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 {font_id} 0 R >> >> /Contents {content_object_ids[index]} 0 R >>".encode(
                "ascii"
            )
        )
        rendered_objects[content_object_ids[index]] = (
            f"<< /Length {len(content_stream)} >>\nstream\n".encode("ascii")
            + content_stream
            + b"\nendstream"
        )

    body_buffer = io.BytesIO()
    body_buffer.write(b"%PDF-1.4\n")
    xref_offsets = [0]
    for object_id in range(1, next_object_id):
        xref_offsets.append(body_buffer.tell())
        body_buffer.write(f"{object_id} 0 obj\n".encode("ascii"))
        body_buffer.write(rendered_objects[object_id])
        body_buffer.write(b"\nendobj\n")

    xref_position = body_buffer.tell()
    body_buffer.write(f"xref\n0 {next_object_id}\n".encode("ascii"))
    body_buffer.write(b"0000000000 65535 f \n")
    for offset in xref_offsets[1:]:
        body_buffer.write(f"{offset:010d} 00000 n \n".encode("ascii"))
    body_buffer.write(
        (
            f"trailer\n<< /Size {next_object_id} /Root {catalog_id} 0 R >>\n"
            f"startxref\n{xref_position}\n%%EOF"
        ).encode("ascii")
    )
    return body_buffer.getvalue()


def _allocation_recipient(allocation):
    if allocation.allocated_to:
        return allocation.allocated_to.get_full_name().strip() or allocation.allocated_to.username
    return _stringify(allocation.allocated_to_lab)


def _request_use_window(item):
    if item.requested_start_at and item.requested_end_at:
        return f"{_stringify(item.requested_start_at)} to {_stringify(item.requested_end_at)}"
    return "-"


def _stringify(value):
    if value is None or value == "":
        return "-"
    if isinstance(value, datetime.datetime):
        return value.strftime("%b %d, %Y %H:%M")
    if isinstance(value, datetime.date):
        return value.strftime("%b %d, %Y")
    if isinstance(value, Decimal):
        return f"{value:.2f}"
    return str(value)


def _truncate_sheet_name(name):
    cleaned = (name or "Report").replace("/", "-").replace("\\", "-").replace("?", "")
    return cleaned[:31]


def _cell(value, *, style=None, merge_across=None):
    style_attr = f' ss:StyleID="{style}"' if style else ""
    merge_attr = f' ss:MergeAcross="{merge_across}"' if merge_across is not None else ""
    return f'    <Cell{style_attr}{merge_attr}><Data ss:Type="String">{escape(_stringify(value))}</Data></Cell>'


def _typed_cell(value):
    if isinstance(value, bool):
        cell_type = "String"
        rendered_value = "Yes" if value else "No"
    elif isinstance(value, (int, float, Decimal)) and value is not None:
        cell_type = "Number"
        rendered_value = str(value)
    else:
        cell_type = "String"
        rendered_value = _stringify(value)
    return f'    <Cell><Data ss:Type="{cell_type}">{escape(rendered_value)}</Data></Cell>'


def _merged_row(value, merge_across, style):
    return f'   <Row>{_cell(value, style=style, merge_across=merge_across)}</Row>'


def _build_pdf_lines(payload):
    lines = [
        (18, payload["title"]),
        (12, payload["heading"]),
        (10, f'Generated By: {payload["generated_by"]}'),
        (10, f'Generated On: {payload["generated_at"].strftime("%b %d, %Y %H:%M")}'),
        (10, f'Active Filters: {payload["filters_text"]}'),
        (0, ""),
    ]

    for label, value in payload["summary_pairs"]:
        lines.append((10, f"{label}: {value}"))

    lines.append((0, ""))
    if not payload["rows"]:
        lines.append((11, "No rows matched the current filters."))
        return lines

    for index, row in enumerate(payload["rows"], start=1):
        row_parts = [f"{column}: {_stringify(value)}" for column, value in zip(payload["columns"], row)]
        wrapped_parts = textwrap.wrap(" | ".join(row_parts), width=94)
        if wrapped_parts:
            lines.append((11, f"{index}. {wrapped_parts[0]}"))
            for extra_line in wrapped_parts[1:]:
                lines.append((10, extra_line))
        else:
            lines.append((11, f"{index}."))
        lines.append((0, ""))

    return lines


def _paginate_pdf_lines(lines):
    pages = []
    current_page = []
    current_y = 800
    line_gap = 6

    for font_size, text in lines:
        effective_size = font_size or 10
        height_cost = effective_size + line_gap if text else 8
        if current_y - height_cost < 40 and current_page:
            pages.append(current_page)
            current_page = []
            current_y = 800

        current_page.append((font_size, text, current_y))
        current_y -= height_cost

    if current_page:
        pages.append(current_page)
    return pages or [[(12, "No content available.", 800)]]


def _render_pdf_page_stream(page_lines):
    commands = []
    for font_size, text, y_position in page_lines:
        if not text:
            continue
        escaped_text = _escape_pdf_text(text)
        commands.append(f"BT /F1 {font_size} Tf 40 {y_position} Td ({escaped_text}) Tj ET")
    return "\n".join(commands).encode("ascii", "ignore")


def _escape_pdf_text(text):
    return str(text).replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
