from django.contrib import admin
from .models import User

@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ('id','email','name','nickname','is_staff','is_active','date_joined')
    search_fields = ('email','name','nickname')
    list_filter = ('is_staff','is_active')
