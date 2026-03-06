"""
File management views for the admin panel.
"""

import os
import re
import uuid
import mimetypes
from datetime import datetime
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.core.paginator import Paginator
from django.http import HttpResponse, Http404, FileResponse
from django.conf import settings
from django.db.models import Q

from core.models import Case, Document
from ..decorators import login_required
from .helpers import session_ctx


# File type icons mapping
FILE_ICONS = {
    'pdf': '📄',
    'doc': '📝',
    'docx': '📝',
    'xls': '📊',
    'xlsx': '📊',
    'jpg': '🖼️',
    'jpeg': '🖼️',
    'png': '🖼️',
    'gif': '🖼️',
    'mp3': '🎵',
    'mp4': '🎬',
    'wav': '🎵',
    'ogg': '🎵',
    'oga': '🎵',
    'txt': '📃',
    'zip': '📦',
    'rar': '📦',
}


def get_file_icon(filename):
    """Get appropriate icon for file type."""
    if not filename:
        return '📁'
    ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''
    return FILE_ICONS.get(ext, '📁')


def get_file_type(filename):
    """Get file type from filename."""
    if not filename:
        return 'unknown'
    ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''
    return ext or 'unknown'


@login_required
def files_list(request):
    """
    List all documents with filter and pagination.
    """
    context = session_ctx(request)
    
    # Get all documents with related case
    documents = Document.objects.select_related('case', 'case__user').order_by('-uploaded_at')
    
    # Search functionality
    search_query = request.GET.get('search', '').strip()
    if search_query:
        documents = documents.filter(
            Q(file_path__icontains=search_query) |
            Q(description__icontains=search_query)
        )
    
    # Filter by case
    case_filter = request.GET.get('case_id', '')
    if case_filter:
        documents = documents.filter(case_id=case_filter)
    
    # Filter by file type
    type_filter = request.GET.get('file_type', '')
    if type_filter:
        documents = documents.filter(file_type=type_filter)
    
    # Pagination (20 per page)
    paginator = Paginator(documents, 20)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)
    
    # Add icons to documents
    for doc in page_obj:
        doc.icon = get_file_icon(doc.file_path)
    
    # Get unique file types for filter dropdown
    file_types = Document.objects.values_list('file_type', flat=True).distinct()
    
    context.update({
        'page_title': 'Files',
        'page_obj': page_obj,
        'search_query': search_query,
        'case_filter': case_filter,
        'type_filter': type_filter,
        'file_types': [ft for ft in file_types if ft],
        'total_count': paginator.count,
    })
    
    return render(request, 'panel/files_list.html', context)


@login_required
def file_upload(request):
    """
    Upload a new file/document.
    """
    context = session_ctx(request)
    
    if request.method == 'POST':
        case_id = request.POST.get('case_id', '').strip()
        description = request.POST.get('description', '').strip() or None
        uploaded_file = request.FILES.get('file')
        
        # Validation
        if not case_id:
            messages.error(request, 'Case is required.')
            return render(request, 'panel/file_upload.html', context)
        
        if not uploaded_file:
            messages.error(request, 'Please select a file to upload.')
            return render(request, 'panel/file_upload.html', context)
        
        try:
            case = Case.objects.get(pk=case_id)
        except Case.DoesNotExist:
            messages.error(request, 'Selected case does not exist.')
            return render(request, 'panel/file_upload.html', context)
        
        # Save file to uploads directory
        uploads_dir = settings.MEDIA_ROOT
        os.makedirs(uploads_dir, exist_ok=True)
        
        # Generate unique filename
        file_ext = uploaded_file.name.rsplit('.', 1)[-1] if '.' in uploaded_file.name else ''
        unique_id = str(uuid.uuid4())[:8]
        safe_filename = f"{unique_id}_{uploaded_file.name}"
        file_path = os.path.join(uploads_dir, safe_filename)
        
        # Write file
        with open(file_path, 'wb+') as destination:
            for chunk in uploaded_file.chunks():
                destination.write(chunk)
        
        # Determine file type
        file_type = get_file_type(uploaded_file.name)
        
        # Create document record
        document = Document.objects.create(
            case=case,
            file_path=uploaded_file.name,
            file_type=file_type,
            telegram_file_id=f"local:{safe_filename}",
            file_unique_id=unique_id,
            media_type='document',
            description=description,
        )
        
        messages.success(request, f'File "{uploaded_file.name}" uploaded successfully.')
        return redirect('panel:files_list')
    
    # Get cases for dropdown
    cases = Case.objects.select_related('user').order_by('-created_at')[:100]
    
    context.update({
        'page_title': 'Upload File',
        'cases': cases,
    })
    
    return render(request, 'panel/file_upload.html', context)


@login_required
def file_view(request, doc_id):
    """
    View/download a document.
    """
    document = get_object_or_404(Document, pk=doc_id)
    
    # Check if it's a local file
    file_id = document.telegram_file_id or ''
    
    if file_id.startswith('local:'):
        # Local file
        filename = file_id[6:]  # Remove 'local:' prefix
        file_path = os.path.join(settings.MEDIA_ROOT, filename)
        
        if not os.path.exists(file_path):
            raise Http404('File not found on server.')
        
        # Content type from filename so browser can display/play when appropriate
        content_type, _ = mimetypes.guess_type(filename)
        media_type = (document.media_type or '').lower()
        if not content_type:
            if media_type == 'photo':
                content_type = 'image/jpeg'
            elif media_type == 'voice':
                content_type = 'audio/ogg'
            elif media_type == 'video':
                content_type = 'video/mp4'
        if not content_type:
            content_type = 'application/octet-stream'
        # Viewable = image/audio/video so browser opens inline instead of downloading
        viewable = (
            media_type in ('photo', 'voice', 'video') or
            content_type.startswith('image/') or
            content_type.startswith('audio/') or
            content_type.startswith('video/')
        )
        
        # Use display name for download filename when set
        disp_name = document.display_name or document.file_path or filename
        
        download = request.GET.get('download', False)
        if download or not viewable:
            response = FileResponse(open(file_path, 'rb'), content_type=content_type)
            response['Content-Disposition'] = f'attachment; filename="{disp_name}"'
        else:
            response = FileResponse(open(file_path, 'rb'), content_type=content_type)
            response['Content-Disposition'] = f'inline; filename="{disp_name}"'
        
        return response
    
    # For Telegram files, we'd need to use the Telegram API
    # For now, just show an error
    raise Http404('Remote file viewing not implemented yet.')


@login_required
def file_detail(request, doc_id):
    """
    View file details page.
    """
    context = session_ctx(request)
    
    document = get_object_or_404(Document.objects.select_related('case', 'case__user'), pk=doc_id)
    
    # Add icon
    document.icon = get_file_icon(document.file_path)
    
    # Check if file exists locally
    file_exists = False
    file_id = document.telegram_file_id or ''
    if file_id.startswith('local:'):
        filename = file_id[6:]
        file_path = os.path.join(settings.MEDIA_ROOT, filename)
        file_exists = os.path.exists(file_path)
    
    context.update({
        'page_title': f'File: {document.display_name or document.file_path or "Document"}',
        'document': document,
        'file_exists': file_exists,
    })
    
    return render(request, 'panel/file_detail.html', context)


@login_required
def file_rename(request, doc_id):
    """
    Update document display name (POST only).
    """
    if request.method != 'POST':
        return redirect('panel:file_detail', doc_id=doc_id)
    document = get_object_or_404(Document, pk=doc_id)
    new_name = (request.POST.get('display_name') or '').strip()
    if new_name:
        # Sanitize: allow alphanumeric, dots, underscores, hyphens, spaces
        new_name = re.sub(r'[^\w.\- ]', '', new_name)[:255].strip()
    document.display_name = new_name or None
    document.save(update_fields=['display_name'])
    messages.success(request, 'File name updated.')
    return redirect('panel:file_detail', doc_id=doc_id)


@login_required
def file_delete(request, doc_id):
    """
    Delete a document.
    """
    if request.method != 'POST':
        return redirect('panel:files_list')
    
    document = get_object_or_404(Document, pk=doc_id)
    
    # Delete local file if exists
    file_id = document.telegram_file_id or ''
    if file_id.startswith('local:'):
        filename = file_id[6:]
        file_path = os.path.join(settings.MEDIA_ROOT, filename)
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
            except OSError:
                pass
    
    filename = document.file_path or 'Document'
    document.delete()
    
    messages.success(request, f'File "{filename}" deleted successfully.')
    return redirect('panel:files_list')
