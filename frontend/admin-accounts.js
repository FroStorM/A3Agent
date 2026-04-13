const { createApp, ref, computed, onMounted } = Vue;

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
        const adminUserSearch = ref('');
        const adminRoleFilter = ref('all');
        const adminStatusFilter = ref('all');

        const createUsername = ref('');
        const createPassword = ref('');
        const createIsAdmin = ref(false);
        const adminResetPassword = ref('');
        const adminLimitParallel = ref(1);
        const adminLimitPrompt = ref(20000);
        const adminLimitUploadMb = ref(10);

        const isAdmin = computed(() => !!(currentUser.value && currentUser.value.is_admin));
        const selectedAdminUser = computed(() => adminUsers.value.find((u) => u.username === selectedAdminUsername.value) || null);

        const syncSelectedAdminLimits = () => {
            const user = selectedAdminUser.value;
            if (!user) return;
            adminLimitParallel.value = Number(user.max_parallel_runs || 1);
            adminLimitPrompt.value = Number(user.max_prompt_chars || 20000);
            adminLimitUploadMb.value = Math.max(1, Math.round(Number(user.max_upload_bytes || 10485760) / (1024 * 1024)));
        };

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
                } else if (selectedAdminUsername.value && !adminUsers.value.some((u) => u.username === selectedAdminUsername.value)) {
                    selectedAdminUsername.value = adminUsers.value.length ? adminUsers.value[0].username : '';
                }
                syncSelectedAdminLimits();
                return true;
            } catch (e) {
                adminError.value = String(e && e.message ? e.message : e);
                return false;
            } finally {
                adminBusy.value = false;
            }
        };

        const chooseAdminUser = (username) => {
            selectedAdminUsername.value = username || '';
            syncSelectedAdminLimits();
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
                adminNotice.value = `已重置 ${selectedAdminUsername.value} 的密码`;
                await fetchAdminUsers();
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
            } catch (e) {
                adminError.value = String(e && e.message ? e.message : e);
            } finally {
                adminBusy.value = false;
            }
        };

        const initialize = async () => {
            const ok = await fetchAuthMe();
            if (!ok || !isAdmin.value) return;
            await fetchAdminUsers();
        };

        onMounted(initialize);

        return {
            authReady, currentUser, isAdmin, loginUsername, loginPassword, loginBusy, authError, login, logout,
            adminBusy, adminError, adminNotice, adminUsers, selectedAdminUsername, selectedAdminUser, adminUserSearch,
            adminRoleFilter, adminStatusFilter, createUsername, createPassword, createIsAdmin, adminResetPassword,
            adminLimitParallel, adminLimitPrompt, adminLimitUploadMb, chooseAdminUser, fetchAdminUsers, createAdminUser,
            adminResetUserPassword, adminToggleUserStatus, saveAdminLimits,
        };
    }
}).mount('#admin-accounts-app');
