const { createApp, ref, computed, onMounted, nextTick } = Vue;

createApp({
    setup() {
        const authReady = ref(false);
        const currentUser = ref(null);
        const loginUsername = ref('admin');
        const loginPassword = ref('');
        const loginBusy = ref(false);
        const authError = ref('');

        const adminBusy = ref(false);
        const adminError = ref('');
        const adminNotice = ref('');

        const adminUsers = ref([]);
        const selectedAdminUsername = ref('');
        const adminScope = ref('memory');
        const adminFiles = ref([]);
        const selectedAdminFilePath = ref('');
        const adminFileContent = ref('');
        const adminFileDraft = ref('');
        const adminFileEditMode = ref(false);

        const adminUserSearch = ref('');
        const adminRoleFilter = ref('all');
        const adminStatusFilter = ref('all');
        const adminSelectedTargets = ref([]);

        const createUsername = ref('');
        const createPassword = ref('');
        const createIsAdmin = ref(false);
        const adminResetPassword = ref('');
        const adminLimitParallel = ref(1);
        const adminLimitPrompt = ref(20000);
        const adminLimitUploadMb = ref(10);

        const copyTargetUsername = ref('');
        const copyTargetPath = ref('');
        const batchCopyPath = ref('');
        const adminUploadPath = ref('');
        const adminUploadFileName = ref('');
        const adminCreatePath = ref('');
        const adminCreateKind = ref('file');
        const adminRenamePath = ref('');

        const auditLogs = ref([]);
        const auditActionFilter = ref('');
        const auditTargetFilter = ref('');

        const isAdmin = computed(() => !!(currentUser.value && currentUser.value.is_admin));
        const selectedAdminUser = computed(() => adminUsers.value.find((user) => user.username === selectedAdminUsername.value) || null);
        const filteredAdminUsers = computed(() => adminUsers.value);
        const allFilteredTargetsSelected = computed(() => {
            const candidates = filteredAdminUsers.value.map((user) => user.username).filter((name) => name !== selectedAdminUsername.value);
            return candidates.length > 0 && candidates.every((name) => adminSelectedTargets.value.includes(name));
        });

        const syncSelectedAdminLimits = () => {
            const user = selectedAdminUser.value;
            if (!user) return;
            adminLimitParallel.value = Number(user.max_parallel_runs || 1);
            adminLimitPrompt.value = Number(user.max_prompt_chars || 20000);
            adminLimitUploadMb.value = Math.max(1, Math.round(Number(user.max_upload_bytes || 10485760) / (1024 * 1024)));
        };

        const renderIcons = () => nextTick(() => { if (window.lucide) lucide.createIcons(); });

        const fetchAuthMe = async () => {
            try {
                const res = await fetch('/api/auth/me');
                const data = await res.json().catch(() => ({}));
                currentUser.value = data && data.authenticated ? data.user : null;
                authReady.value = true;
                return !!currentUser.value;
            } catch (e) {
                currentUser.value = null;
                authReady.value = true;
                return false;
            }
        };

        const login = async () => {
            try {
                loginBusy.value = true;
                authError.value = '';
                const res = await fetch('/api/auth/login', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ username: loginUsername.value || '', password: loginPassword.value || '' }),
                });
                const data = await res.json().catch(() => ({}));
                if (!res.ok) {
                    authError.value = data.error || '登录失败';
                    return false;
                }
                loginPassword.value = '';
                await initialize();
                return true;
            } catch (e) {
                authError.value = String(e && e.message ? e.message : e);
                return false;
            } finally {
                loginBusy.value = false;
            }
        };

        const logout = async () => {
            try {
                await fetch('/api/auth/logout', { method: 'POST' });
            } catch (e) {}
            currentUser.value = null;
            authReady.value = true;
        };

        const fetchAdminUsers = async () => {
            if (!isAdmin.value) return false;
            try {
                adminBusy.value = true;
                adminError.value = '';
                const params = new URLSearchParams({
                    q: adminUserSearch.value || '',
                    role: adminRoleFilter.value || 'all',
                    status: adminStatusFilter.value || 'all',
                    page: '1',
                    page_size: '200',
                });
                const res = await fetch(`/api/admin/users?${params.toString()}`);
                const data = await res.json().catch(() => ({}));
                if (!res.ok) {
                    adminError.value = data.error || '加载用户列表失败';
                    return false;
                }
                adminUsers.value = data.users || [];
                if (!selectedAdminUsername.value && adminUsers.value.length) {
                    selectedAdminUsername.value = adminUsers.value[0].username;
                    copyTargetUsername.value = adminUsers.value[0].username;
                } else if (selectedAdminUsername.value && !adminUsers.value.some((user) => user.username === selectedAdminUsername.value)) {
                    selectedAdminUsername.value = adminUsers.value.length ? adminUsers.value[0].username : '';
                }
                syncSelectedAdminLimits();
                const validTargets = new Set(adminUsers.value.map((user) => user.username));
                adminSelectedTargets.value = adminSelectedTargets.value.filter((username) => validTargets.has(username));
                if (!copyTargetUsername.value || !validTargets.has(copyTargetUsername.value)) {
                    copyTargetUsername.value = adminUsers.value.length ? adminUsers.value[0].username : '';
                }
                return true;
            } catch (e) {
                adminError.value = String(e && e.message ? e.message : e);
                return false;
            } finally {
                adminBusy.value = false;
            }
        };

        const fetchAdminFiles = async () => {
            if (!isAdmin.value || !selectedAdminUsername.value) return false;
            try {
                adminBusy.value = true;
                adminError.value = '';
                adminNotice.value = '';
                adminFiles.value = [];
                adminFileContent.value = '';
                selectedAdminFilePath.value = '';
                const res = await fetch(`/api/admin/files/tree?username=${encodeURIComponent(selectedAdminUsername.value)}&scope=${encodeURIComponent(adminScope.value)}`);
                const data = await res.json().catch(() => ({}));
                if (!res.ok) {
                    adminError.value = data.error || '加载文件列表失败';
                    return false;
                }
                adminFiles.value = data.items || [];
                renderIcons();
                return true;
            } catch (e) {
                adminError.value = String(e && e.message ? e.message : e);
                return false;
            } finally {
                adminBusy.value = false;
            }
        };

        const selectAdminFile = async (path) => {
            if (!path || !selectedAdminUsername.value) return;
            try {
                adminBusy.value = true;
                adminError.value = '';
                adminNotice.value = '';
                selectedAdminFilePath.value = path;
                copyTargetPath.value = path;
                batchCopyPath.value = path;
                adminUploadPath.value = path;
                adminRenamePath.value = path;
                adminFileEditMode.value = false;
                const res = await fetch(`/api/admin/files/read?username=${encodeURIComponent(selectedAdminUsername.value)}&scope=${encodeURIComponent(adminScope.value)}&path=${encodeURIComponent(path)}`);
                const data = await res.json().catch(() => ({}));
                if (!res.ok) {
                    adminError.value = data.error || '读取文件失败';
                    adminFileContent.value = '';
                    adminFileDraft.value = '';
                    return;
                }
                adminFileContent.value = data.content || '';
                adminFileDraft.value = data.content || '';
            } catch (e) {
                adminError.value = String(e && e.message ? e.message : e);
            } finally {
                adminBusy.value = false;
            }
        };

        const chooseAdminUser = async (username) => {
            selectedAdminUsername.value = username || '';
            copyTargetUsername.value = username || '';
            syncSelectedAdminLimits();
            await fetchAdminFiles();
        };

        const createAdminUser = async () => {
            try {
                adminBusy.value = true;
                adminError.value = '';
                adminNotice.value = '';
                const res = await fetch('/api/admin/users', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        username: createUsername.value,
                        password: createPassword.value,
                        is_admin: createIsAdmin.value,
                    }),
                });
                const data = await res.json().catch(() => ({}));
                if (!res.ok) {
                    adminError.value = data.error || '创建用户失败';
                    return;
                }
                createUsername.value = '';
                createPassword.value = '';
                createIsAdmin.value = false;
                adminNotice.value = '用户已创建';
                await fetchAdminUsers();
                await fetchAuditLogs();
            } catch (e) {
                adminError.value = String(e && e.message ? e.message : e);
            } finally {
                adminBusy.value = false;
            }
        };

        const adminResetUserPassword = async () => {
            try {
                adminBusy.value = true;
                adminError.value = '';
                adminNotice.value = '';
                const res = await fetch('/api/admin/users/password', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ username: selectedAdminUsername.value, new_password: adminResetPassword.value }),
                });
                const data = await res.json().catch(() => ({}));
                if (!res.ok) {
                    adminError.value = data.error || '重置密码失败';
                    return;
                }
                adminResetPassword.value = '';
                adminNotice.value = '密码已重置';
                await fetchAdminUsers();
                await fetchAuditLogs();
            } catch (e) {
                adminError.value = String(e && e.message ? e.message : e);
            } finally {
                adminBusy.value = false;
            }
        };

        const adminToggleUserStatus = async (nextActive) => {
            try {
                adminBusy.value = true;
                adminError.value = '';
                adminNotice.value = '';
                const res = await fetch('/api/admin/users/status', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ username: selectedAdminUsername.value, is_active: !!nextActive }),
                });
                const data = await res.json().catch(() => ({}));
                if (!res.ok) {
                    adminError.value = data.error || '更新状态失败';
                    return;
                }
                adminNotice.value = nextActive ? '账号已启用' : '账号已禁用';
                await fetchAdminUsers();
                await fetchAuditLogs();
            } catch (e) {
                adminError.value = String(e && e.message ? e.message : e);
            } finally {
                adminBusy.value = false;
            }
        };

        const saveAdminLimits = async () => {
            try {
                adminBusy.value = true;
                adminError.value = '';
                adminNotice.value = '';
                const res = await fetch('/api/admin/users/limits', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        username: selectedAdminUsername.value,
                        max_parallel_runs: Number(adminLimitParallel.value || 1),
                        max_prompt_chars: Number(adminLimitPrompt.value || 20000),
                        max_upload_bytes: Number(adminLimitUploadMb.value || 10) * 1024 * 1024,
                    }),
                });
                const data = await res.json().catch(() => ({}));
                if (!res.ok) {
                    adminError.value = data.error || '保存配额失败';
                    return;
                }
                adminNotice.value = '用户配额已更新';
                await fetchAdminUsers();
                await fetchAuditLogs();
            } catch (e) {
                adminError.value = String(e && e.message ? e.message : e);
            } finally {
                adminBusy.value = false;
            }
        };

        const startEditAdminFile = () => {
            adminFileDraft.value = adminFileContent.value || '';
            adminFileEditMode.value = true;
        };

        const cancelEditAdminFile = () => {
            adminFileDraft.value = adminFileContent.value || '';
            adminFileEditMode.value = false;
        };

        const saveAdminFile = async () => {
            try {
                adminBusy.value = true;
                adminError.value = '';
                adminNotice.value = '';
                const res = await fetch('/api/admin/files/write', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        username: selectedAdminUsername.value,
                        scope: adminScope.value,
                        path: selectedAdminFilePath.value,
                        content: adminFileDraft.value || '',
                    }),
                });
                const data = await res.json().catch(() => ({}));
                if (!res.ok) {
                    adminError.value = data.error || '保存文件失败';
                    return;
                }
                adminFileContent.value = adminFileDraft.value || '';
                adminFileEditMode.value = false;
                adminNotice.value = '文件已保存';
                await fetchAuditLogs();
            } catch (e) {
                adminError.value = String(e && e.message ? e.message : e);
            } finally {
                adminBusy.value = false;
            }
        };

        const createAdminPath = async () => {
            try {
                adminBusy.value = true;
                adminError.value = '';
                adminNotice.value = '';
                const createdPath = adminCreatePath.value;
                const kind = adminCreateKind.value;
                const res = await fetch('/api/admin/files/create', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        username: selectedAdminUsername.value,
                        scope: adminScope.value,
                        path: createdPath,
                        kind,
                    }),
                });
                const data = await res.json().catch(() => ({}));
                if (!res.ok) {
                    adminError.value = data.error || '创建失败';
                    return;
                }
                adminCreatePath.value = '';
                adminNotice.value = kind === 'dir' ? '文件夹已创建' : '文件已创建';
                await fetchAdminFiles();
                if (kind === 'file') await selectAdminFile(createdPath);
                await fetchAuditLogs();
            } catch (e) {
                adminError.value = String(e && e.message ? e.message : e);
            } finally {
                adminBusy.value = false;
            }
        };

        const renameAdminPath = async () => {
            try {
                adminBusy.value = true;
                adminError.value = '';
                adminNotice.value = '';
                const res = await fetch('/api/admin/files/rename', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        username: selectedAdminUsername.value,
                        scope: adminScope.value,
                        old_path: selectedAdminFilePath.value,
                        new_path: adminRenamePath.value,
                    }),
                });
                const data = await res.json().catch(() => ({}));
                if (!res.ok) {
                    adminError.value = data.error || '重命名失败';
                    return;
                }
                adminNotice.value = '路径已重命名';
                await fetchAdminFiles();
                await selectAdminFile(adminRenamePath.value);
                await fetchAuditLogs();
            } catch (e) {
                adminError.value = String(e && e.message ? e.message : e);
            } finally {
                adminBusy.value = false;
            }
        };

        const deleteAdminPath = async () => {
            if (!selectedAdminFilePath.value) return;
            if (!window.confirm(`确认删除 ${selectedAdminFilePath.value} 吗？`)) return;
            try {
                adminBusy.value = true;
                adminError.value = '';
                adminNotice.value = '';
                const res = await fetch('/api/admin/files/delete', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        username: selectedAdminUsername.value,
                        scope: adminScope.value,
                        path: selectedAdminFilePath.value,
                    }),
                });
                const data = await res.json().catch(() => ({}));
                if (!res.ok) {
                    adminError.value = data.error || '删除失败';
                    return;
                }
                adminNotice.value = '路径已删除';
                selectedAdminFilePath.value = '';
                adminFileContent.value = '';
                adminFileDraft.value = '';
                await fetchAdminFiles();
                await fetchAuditLogs();
            } catch (e) {
                adminError.value = String(e && e.message ? e.message : e);
            } finally {
                adminBusy.value = false;
            }
        };

        const copyAdminFile = async () => {
            try {
                adminBusy.value = true;
                adminError.value = '';
                adminNotice.value = '';
                const res = await fetch('/api/admin/files/copy', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        source_username: selectedAdminUsername.value,
                        target_username: copyTargetUsername.value,
                        scope: adminScope.value,
                        path: selectedAdminFilePath.value,
                        target_path: copyTargetPath.value || selectedAdminFilePath.value,
                    }),
                });
                const data = await res.json().catch(() => ({}));
                if (!res.ok) {
                    adminError.value = data.error || '复制失败';
                    return;
                }
                adminNotice.value = `已复制到 ${copyTargetUsername.value}`;
                await fetchAuditLogs();
            } catch (e) {
                adminError.value = String(e && e.message ? e.message : e);
            } finally {
                adminBusy.value = false;
            }
        };

        const toggleAdminTarget = (username) => {
            if (!username || username === selectedAdminUsername.value) return;
            if (adminSelectedTargets.value.includes(username)) {
                adminSelectedTargets.value = adminSelectedTargets.value.filter((item) => item !== username);
            } else {
                adminSelectedTargets.value = [...adminSelectedTargets.value, username];
            }
        };

        const toggleAllFilteredTargets = () => {
            const candidates = filteredAdminUsers.value.map((user) => user.username).filter((name) => name !== selectedAdminUsername.value);
            if (allFilteredTargetsSelected.value) {
                adminSelectedTargets.value = adminSelectedTargets.value.filter((name) => !candidates.includes(name));
            } else {
                adminSelectedTargets.value = Array.from(new Set([...adminSelectedTargets.value, ...candidates]));
            }
        };

        const batchCopyAdminFile = async () => {
            try {
                adminBusy.value = true;
                adminError.value = '';
                adminNotice.value = '';
                const res = await fetch('/api/admin/files/copy_batch', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        source_username: selectedAdminUsername.value,
                        target_usernames: adminSelectedTargets.value,
                        scope: adminScope.value,
                        path: selectedAdminFilePath.value,
                        target_path: batchCopyPath.value || selectedAdminFilePath.value,
                    }),
                });
                const data = await res.json().catch(() => ({}));
                if (!res.ok) {
                    adminError.value = data.error || '批量分发失败';
                    return;
                }
                adminNotice.value = `已分发到 ${(data.copied || []).length} 个用户`;
                await fetchAuditLogs();
            } catch (e) {
                adminError.value = String(e && e.message ? e.message : e);
            } finally {
                adminBusy.value = false;
            }
        };

        const uploadAdminFile = async (event) => {
            const input = event && event.target;
            const file = input && input.files && input.files[0];
            if (!file) return;
            try {
                adminBusy.value = true;
                adminError.value = '';
                adminNotice.value = '';
                const form = new FormData();
                form.append('source_username', selectedAdminUsername.value);
                form.append('scope', adminScope.value);
                form.append('target_path', adminUploadPath.value || file.name);
                form.append('file', file);
                const res = await fetch('/api/admin/files/upload', { method: 'POST', body: form });
                const data = await res.json().catch(() => ({}));
                if (!res.ok) {
                    adminError.value = data.error || '上传失败';
                    return;
                }
                adminUploadFileName.value = file.name;
                adminNotice.value = `已上传 ${file.name}`;
                await fetchAdminFiles();
                if (data.path) await selectAdminFile(data.path);
                await fetchAuditLogs();
            } catch (e) {
                adminError.value = String(e && e.message ? e.message : e);
            } finally {
                adminBusy.value = false;
                if (input) input.value = '';
            }
        };

        const fetchAuditLogs = async () => {
            try {
                const params = new URLSearchParams({
                    action: auditActionFilter.value || '',
                    target_username: auditTargetFilter.value || '',
                    limit: '80',
                });
                const res = await fetch(`/api/admin/audit_logs?${params.toString()}`);
                const data = await res.json().catch(() => ({}));
                if (!res.ok) {
                    adminError.value = data.error || '加载审计日志失败';
                    return false;
                }
                auditLogs.value = data.logs || [];
                return true;
            } catch (e) {
                adminError.value = String(e && e.message ? e.message : e);
                return false;
            }
        };

        const formatAuditTime = (ts) => {
            try {
                return new Date(ts * 1000).toLocaleString();
            } catch (e) {
                return String(ts || '');
            }
        };

        const initialize = async () => {
            const ok = await fetchAuthMe();
            if (!ok) return;
            if (!isAdmin.value) return;
            await fetchAdminUsers();
            if (selectedAdminUsername.value) await fetchAdminFiles();
            await fetchAuditLogs();
            renderIcons();
        };

        onMounted(async () => {
            await initialize();
            renderIcons();
        });

        return {
            authReady, currentUser, isAdmin, loginUsername, loginPassword, loginBusy, authError, login, logout,
            adminBusy, adminError, adminNotice, adminUsers, selectedAdminUsername, selectedAdminUser, adminScope, adminFiles,
            selectedAdminFilePath, adminFileContent, adminFileDraft, adminFileEditMode, adminUserSearch, adminRoleFilter,
            adminStatusFilter, filteredAdminUsers, adminSelectedTargets, allFilteredTargetsSelected, createUsername,
            createPassword, createIsAdmin, adminResetPassword, adminLimitParallel, adminLimitPrompt, adminLimitUploadMb,
            copyTargetUsername, copyTargetPath, batchCopyPath, adminUploadPath, adminUploadFileName, adminCreatePath,
            adminCreateKind, adminRenamePath, auditLogs, auditActionFilter, auditTargetFilter, chooseAdminUser,
            fetchAdminUsers, fetchAdminFiles, selectAdminFile, createAdminUser, adminResetUserPassword,
            adminToggleUserStatus, saveAdminLimits, startEditAdminFile, cancelEditAdminFile, saveAdminFile,
            createAdminPath, renameAdminPath, deleteAdminPath, copyAdminFile, toggleAdminTarget, toggleAllFilteredTargets,
            batchCopyAdminFile, uploadAdminFile, fetchAuditLogs, formatAuditTime,
        };
    }
}).mount('#admin-app');
