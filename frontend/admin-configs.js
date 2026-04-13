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
        const adminFiles = ref([]);
        const selectedAdminFilePath = ref('');
        const adminFileContent = ref('');
        const adminFileDraft = ref('');
        const adminFileEditMode = ref(false);
        const adminUploadPath = ref('');

        const distributeModalOpen = ref(false);
        const distributeTargets = ref([]);
        const distributeTargetPath = ref('');

        const isAdmin = computed(() => !!(currentUser.value && currentUser.value.is_admin));
        const distributableUsers = computed(() => adminUsers.value.filter((u) => u.username !== selectedAdminUsername.value));
        const allTargetsSelected = computed(() => distributableUsers.value.length > 0 && distributableUsers.value.every((u) => distributeTargets.value.includes(u.username)));

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
            try {
                adminError.value = '';
                const res = await fetch('/api/admin/users?page=1&page_size=200');
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
                return true;
            } catch (e) {
                adminError.value = String(e && e.message ? e.message : e);
                return false;
            }
        };

        const fetchAdminFiles = async () => {
            if (!selectedAdminUsername.value) return false;
            try {
                adminBusy.value = true;
                adminError.value = '';
                adminNotice.value = '';
                adminFiles.value = [];
                selectedAdminFilePath.value = '';
                adminFileContent.value = '';
                adminFileDraft.value = '';
                adminUploadPath.value = '';
                adminFileEditMode.value = false;
                const res = await fetch(`/api/admin/files/tree?username=${encodeURIComponent(selectedAdminUsername.value)}&scope=config`);
                const data = await res.json().catch(() => ({}));
                if (!res.ok) {
                    adminError.value = data.error || '加载配置文件失败';
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
                adminFileEditMode.value = false;
                selectedAdminFilePath.value = path;
                adminUploadPath.value = path;
                const res = await fetch(`/api/admin/files/read?username=${encodeURIComponent(selectedAdminUsername.value)}&scope=config&path=${encodeURIComponent(path)}`);
                const data = await res.json().catch(() => ({}));
                if (!res.ok) {
                    adminError.value = data.error || '读取文件失败';
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
            await fetchAdminFiles();
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
            if (!selectedAdminFilePath.value) {
                adminError.value = '请先选择一个配置文件';
                return;
            }
            try {
                adminBusy.value = true;
                adminError.value = '';
                adminNotice.value = '';
                const res = await fetch('/api/admin/files/write', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        username: selectedAdminUsername.value,
                        scope: 'config',
                        path: selectedAdminFilePath.value,
                        content: adminFileDraft.value || '',
                    }),
                });
                const data = await res.json().catch(() => ({}));
                if (!res.ok) {
                    adminError.value = data.error || '保存失败';
                    return;
                }
                adminFileContent.value = adminFileDraft.value || '';
                adminFileEditMode.value = false;
                adminNotice.value = '配置文件已保存';
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
            if (!selectedAdminUsername.value) {
                adminError.value = '请先选择用户';
                if (input) input.value = '';
                return;
            }
            try {
                adminBusy.value = true;
                adminError.value = '';
                adminNotice.value = '';
                const form = new FormData();
                form.append('source_username', selectedAdminUsername.value);
                form.append('scope', 'config');
                form.append('target_path', adminUploadPath.value || file.name);
                form.append('file', file);
                const res = await fetch('/api/admin/files/upload', { method: 'POST', body: form });
                const data = await res.json().catch(() => ({}));
                if (!res.ok) {
                    adminError.value = data.error || '上传失败';
                    return;
                }
                adminNotice.value = `已上传 ${file.name}`;
                await fetchAdminFiles();
                if (data.path) await selectAdminFile(data.path);
            } catch (e) {
                adminError.value = String(e && e.message ? e.message : e);
            } finally {
                adminBusy.value = false;
                if (input) input.value = '';
            }
        };

        const openDistributeModal = () => {
            if (!selectedAdminFilePath.value) {
                adminError.value = '请先选择一个需要分发的配置文件';
                return;
            }
            distributeTargets.value = [];
            distributeTargetPath.value = selectedAdminFilePath.value || '';
            distributeModalOpen.value = true;
        };

        const closeDistributeModal = () => {
            distributeModalOpen.value = false;
        };

        const toggleTarget = (username) => {
            if (distributeTargets.value.includes(username)) {
                distributeTargets.value = distributeTargets.value.filter((u) => u !== username);
            } else {
                distributeTargets.value = [...distributeTargets.value, username];
            }
        };

        const toggleAllTargets = () => {
            if (allTargetsSelected.value) {
                distributeTargets.value = [];
            } else {
                distributeTargets.value = distributableUsers.value.map((u) => u.username);
            }
        };

        const distributeCurrentFile = async () => {
            if (!selectedAdminFilePath.value) {
                adminError.value = '请先选择一个需要分发的配置文件';
                return;
            }
            if (!distributeTargets.value.length) {
                adminError.value = '请先选择分发目标用户';
                return;
            }
            try {
                adminBusy.value = true;
                adminError.value = '';
                adminNotice.value = '';
                const res = await fetch('/api/admin/files/copy_batch', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        source_username: selectedAdminUsername.value,
                        target_usernames: distributeTargets.value,
                        scope: 'config',
                        path: selectedAdminFilePath.value,
                        target_path: distributeTargetPath.value || selectedAdminFilePath.value,
                    }),
                });
                const data = await res.json().catch(() => ({}));
                if (!res.ok) {
                    adminError.value = data.error || '分发失败';
                    return;
                }
                adminNotice.value = `已分发到 ${(data.copied || []).length} 个用户`;
                distributeModalOpen.value = false;
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
            if (selectedAdminUsername.value) await fetchAdminFiles();
            renderIcons();
        };

        onMounted(initialize);

        return {
            authReady, currentUser, isAdmin, loginUsername, loginPassword, loginBusy, authError, login, logout,
            adminBusy, adminError, adminNotice, adminUsers, selectedAdminUsername, adminFiles, selectedAdminFilePath,
            adminFileContent, adminFileDraft, adminFileEditMode, adminUploadPath, distributeModalOpen, distributeTargets,
            distributeTargetPath, distributableUsers, allTargetsSelected, fetchAdminUsers, fetchAdminFiles, chooseAdminUser,
            selectAdminFile, startEditAdminFile, cancelEditAdminFile, saveAdminFile, uploadAdminFile, openDistributeModal,
            closeDistributeModal, toggleTarget, toggleAllTargets, distributeCurrentFile,
        };
    }
}).mount('#admin-configs-app');
