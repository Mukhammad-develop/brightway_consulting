"""
URL configuration for admin panel.
"""

from django.urls import path
from .views import auth, dashboard, users, cases, files, services, reports, notifications, team, import_chat

app_name = 'panel'

urlpatterns = [
    # Authentication
    path('admin/login', auth.login_view, name='login'),
    path('admin/logout', auth.logout_view, name='logout'),
    path('admin/profile', auth.profile_view, name='profile'),
    path('admin/theme-toggle', auth.theme_toggle_view, name='theme_toggle'),
    
    # Dashboard
    path('admin', dashboard.dashboard, name='dashboard'),
    path('admin/', dashboard.dashboard),
    
    # Users Management
    path('admin/users', users.users_list, name='users_list'),
    path('admin/my-clients', users.my_clients, name='my_clients'),
    path('admin/users/add', users.user_add, name='user_add'),
    path('admin/users/<int:user_id>', users.user_detail, name='user_detail'),
    path('admin/users/<int:user_id>/edit', users.user_edit, name='user_edit'),
    
    # User Messaging (Bot Integration)
    path('admin/users/<int:user_id>/send', users.send_message, name='send_message'),
    path('admin/users/<int:user_id>/poll', users.poll_messages, name='poll_messages'),
    
    # Client Notes
    path('admin/users/<int:user_id>/notes/add', users.note_add, name='note_add'),
    path('admin/users/<int:user_id>/notes/<int:note_id>/edit', users.note_edit, name='note_edit'),
    path('admin/users/<int:user_id>/notes/<int:note_id>/delete', users.note_delete, name='note_delete'),
    path('admin/users/<int:user_id>/notes/<int:note_id>/toggle-pin', users.note_toggle_pin, name='note_toggle_pin'),
    
    # Cases Management
    path('admin/cases', cases.cases_list, name='cases_list'),
    path('admin/cases/add', cases.case_add, name='case_add'),
    path('admin/cases/<int:case_id>', cases.case_detail, name='case_detail'),
    path('admin/cases/<int:case_id>/edit', cases.case_edit, name='case_edit'),
    path('admin/cases/<int:case_id>/update', cases.case_update, name='case_update'),
    path('admin/cases/<int:case_id>/toggle-ai', cases.case_toggle_ai, name='case_toggle_ai'),
    path('admin/cases/<int:case_id>/reimport-chat', cases.case_reimport_chat, name='case_reimport_chat'),

    # Files Management
    path('admin/files', files.files_list, name='files_list'),
    path('admin/files/upload', files.file_upload, name='file_upload'),
    path('admin/files/<int:doc_id>', files.file_detail, name='file_detail'),
    path('admin/files/<int:doc_id>/rename', files.file_rename, name='file_rename'),
    path('admin/files/<int:doc_id>/view', files.file_view, name='file_view'),
    path('admin/files/<int:doc_id>/delete', files.file_delete, name='file_delete'),
    
    # Service Management (elevated users only)
    path('admin/services', services.services_list, name='services_list'),
    path('admin/services/add', services.service_add, name='service_add'),
    path('admin/services/<int:service_id>/edit', services.service_edit, name='service_edit'),
    path('admin/services/<int:service_id>/delete', services.service_delete, name='service_delete'),
    path('admin/services/<int:service_id>/toggle', services.service_toggle, name='service_toggle'),
    path('admin/services/<int:service_id>/steps', services.service_steps, name='service_steps'),
    path('admin/services/<int:service_id>/steps/<int:step_id>/edit', services.step_edit, name='step_edit'),
    path('admin/services/<int:service_id>/test-prompt', services.test_prompt, name='test_prompt'),
    
    # Reports (elevated users only)
    path('admin/reports', reports.reports_dashboard, name='reports'),
    path('admin/reports/generate/<str:report_type>', reports.report_generate, name='report_generate'),
    path('admin/reports/custom', reports.report_custom, name='report_custom'),
    path('admin/reports/<int:report_id>', reports.report_view, name='report_view'),
    path('admin/reports/<int:report_id>/delete', reports.report_delete, name='report_delete'),
    
    # Notifications
    path('admin/notifications', notifications.notifications_list, name='notifications'),
    path('admin/notifications/create', notifications.notification_create, name='notification_create'),
    path('admin/notifications/preview', notifications.notification_preview, name='notification_preview'),
    path('admin/notifications/mark-preview-read', notifications.notification_mark_preview_read, name='notification_mark_preview_read'),
    path('admin/notifications/read-all', notifications.notification_mark_all_read, name='notification_mark_all_read'),
    path('admin/notifications/<int:notification_id>/read', notifications.notification_mark_read, name='notification_mark_read'),
    path('admin/notifications/<int:notification_id>/delete', notifications.notification_delete, name='notification_delete'),
    
    # Team Management (master only)
    path('admin/team', team.team_list, name='team_list'),
    path('admin/team/add', team.team_add, name='team_add'),
    path('admin/team/<int:admin_id>/edit', team.team_edit, name='team_edit'),
    path('admin/team/<int:admin_id>/delete', team.team_delete, name='team_delete'),
    path('admin/team/<int:admin_id>/toggle', team.team_toggle_status, name='team_toggle_status'),
    path('admin/team/<int:admin_id>/assignments', team.team_assignments, name='team_assignments'),
    path('admin/team/<int:admin_id>/reset-password', team.reset_password, name='team_reset_password'),
    
    # Import Chat (elevated users only)
    path('admin/import-chat', import_chat.import_chat_list, name='import_chat'),
    path('admin/import-chat/<int:import_id>/status', import_chat.import_status, name='import_status'),
    path('admin/import-chat/<int:import_id>/cancel', import_chat.import_cancel, name='import_cancel'),
    path('admin/import-chat/<int:import_id>/delete', import_chat.import_delete, name='import_delete'),
]
