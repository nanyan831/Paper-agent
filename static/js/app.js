document.addEventListener('DOMContentLoaded', () => {
    // === 导航与视图切换 ===
    const navItems = document.querySelectorAll('.nav-item');
    const viewSections = document.querySelectorAll('.view-section');

    navItems.forEach(item => {
        item.addEventListener('click', (e) => {
            e.preventDefault();
            const targetView = item.getAttribute('data-view');
            
            // 切换导航 active 状态
            navItems.forEach(nav => nav.classList.remove('active'));
            item.classList.add('active');
            
            // 切换视图
            viewSections.forEach(section => {
                section.classList.add('hidden');
                if(section.id === `view-${targetView}`) {
                    section.classList.remove('hidden');
                    // 触发对应视图的数据加载
                    if(targetView === 'stats') loadStats();
                    if(targetView === 'library') loadLibrary();
                }
            });
        });
    });

    // === 搜索功能 ===
    const searchInput = document.getElementById('searchInput');
    const searchBtn = document.getElementById('searchBtn');
    const searchResults = document.getElementById('searchResults');
    const searchLoading = document.getElementById('searchLoading');

    async function performSearch() {
        const query = searchInput.value.trim();
        if (!query) return;

        const searchType = document.querySelector('input[name="searchType"]:checked').value;
        
        searchResults.innerHTML = '';
        searchLoading.classList.remove('hidden');

        try {
            const res = await fetch(`/api/search?q=${encodeURIComponent(query)}&search_type=${searchType}&top_k=20`);
            const data = await res.json();
            
            searchLoading.classList.add('hidden');
            renderPapers(data.results || [], searchResults);
        } catch (error) {
            console.error('Search failed:', error);
            searchLoading.classList.add('hidden');
            searchResults.innerHTML = `<div class="empty-state"><p style="color: #ef4444;">搜索请求失败: ${error.message}</p></div>`;
        }
    }

    searchBtn.addEventListener('click', performSearch);
    searchInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') performSearch();
    });

    // === 渲染论文列表 ===
    function renderPapers(papers, container) {
        if (!papers || papers.length === 0) {
            container.innerHTML = `
                <div class="empty-state">
                    <i class="fa-solid fa-ghost"></i>
                    <p>未在记忆库中找到相关文献</p>
                </div>`;
            return;
        }

        container.innerHTML = papers.map(paper => `
            <div class="paper-card" data-id="${paper.id}">
                <h3 class="paper-title" onclick="openPaperDetail('${paper.id}')">${paper.title}</h3>
                <div class="paper-meta">
                    ${paper.authors ? `<span><i class="fa-solid fa-users"></i> ${paper.authors}</span>` : ''}
                    <span><i class="fa-regular fa-calendar"></i> ${paper.publish_date || 'Unknown'}</span>
                    ${paper.journal ? `<span><i class="fa-solid fa-book"></i> ${paper.journal}</span>` : ''}
                    <span style="color: var(--accent-primary)">
                        <i class="fa-solid fa-bolt"></i> ${paper.search_type || 'db'}
                    </span>
                </div>
                <div class="paper-abstract">${paper.abstract || '暂无摘要'}</div>
                <div class="paper-actions">
                    <div class="tag-list">
                        <span class="tag">${paper.source}</span>
                        ${paper.language ? `<span class="tag">${paper.language}</span>` : ''}
                    </div>
                    <div>
                        <button class="icon-btn ${paper.is_favorited ? 'active' : ''}" onclick="toggleFavorite('${paper.id}', this)" title="收藏">
                            <i class="fa-solid fa-star"></i>
                        </button>
                        ${paper.url ? `
                        <a href="${paper.url}" target="_blank" class="icon-btn" title="查看原文" onclick="event.stopPropagation()">
                            <i class="fa-solid fa-external-link-alt"></i>
                        </a>` : ''}
                    </div>
                </div>
            </div>
        `).join('');
    }

    // === 弹窗详情 ===
    const modal = document.getElementById('paperModal');
    const modalBody = document.getElementById('modalBody');
    const closeBtn = document.querySelector('.close-btn');

    window.openPaperDetail = async (id) => {
        modal.style.display = 'block';
        modalBody.innerHTML = '<div class="loading-spinner"><div class="spinner"></div></div>';
        
        try {
            const res = await fetch(`/api/papers/${id}`);
            const paper = await res.json();
            
            modalBody.innerHTML = `
                <h2 class="detail-title">${paper.title}</h2>
                <div class="detail-authors">${paper.authors || 'Unknown Authors'}</div>
                
                <div class="paper-meta" style="margin-bottom: 30px; border-bottom: 1px solid var(--border-color); padding-bottom: 20px;">
                    <span><i class="fa-regular fa-calendar"></i> ${paper.publish_date || 'Unknown'}</span>
                    <span><i class="fa-solid fa-book"></i> ${paper.journal || paper.source}</span>
                    <span><i class="fa-solid fa-quote-right"></i> 被引: ${paper.citation_count || 0}</span>
                    ${paper.doi ? `<span>DOI: ${paper.doi}</span>` : ''}
                </div>

                <div class="detail-section">
                    <h4>摘要 Abstract</h4>
                    <div class="detail-abstract">${paper.abstract || 'No abstract available.'}</div>
                </div>

                ${paper.keywords ? `
                <div class="detail-section">
                    <h4>关键词 Keywords</h4>
                    <div class="tag-list" style="flex-wrap: wrap;">
                        ${paper.keywords.split(',').map(k => `<span class="tag">${k.trim()}</span>`).join('')}
                    </div>
                </div>` : ''}

                <div style="margin-top: 30px;">
                    ${paper.url ? `<a href="${paper.url}" target="_blank" class="primary-btn"><i class="fa-solid fa-file-pdf"></i> 获取原文</a>` : ''}
                </div>
            `;
        } catch (error) {
            modalBody.innerHTML = `<p style="color: #ef4444;">加载失败: ${error.message}</p>`;
        }
    };

    closeBtn.onclick = () => modal.style.display = 'none';
    window.onclick = (event) => {
        if (event.target == modal) modal.style.display = 'none';
    };

    // === 交互功能 ===
    window.toggleFavorite = async (id, btn) => {
        event.stopPropagation();
        try {
            const res = await fetch(`/api/papers/${id}/favorite`, { method: 'POST' });
            const data = await res.json();
            if (data.success) {
                if (data.is_favorited) {
                    btn.classList.add('active');
                } else {
                    btn.classList.remove('active');
                }
            }
        } catch (error) {
            console.error('Toggle favorite failed:', error);
        }
    };

    // === 爬虫触发 ===
    document.getElementById('triggerCrawlBtn').addEventListener('click', async () => {
        const source = document.getElementById('crawlSource').value;
        const topic = document.getElementById('crawlTopic').value.trim();
        const btn = document.getElementById('triggerCrawlBtn');
        const logsDiv = document.getElementById('crawlLogs');
        
        btn.disabled = true;
        btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> 正在派遣 Agent...';
        
        try {
            const res = await fetch('/api/crawl/trigger', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ source, topic, max_results: 20 })
            });
            const data = await res.json();
            
            logsDiv.innerHTML = `
                <div style="padding: 16px; background: rgba(16, 185, 129, 0.1); border-left: 4px solid #10b981; border-radius: 4px; margin-top: 20px;">
                    <p style="color: #10b981;"><i class="fa-solid fa-check-circle"></i> ${data.message}</p>
                    <p style="font-size: 13px; color: var(--text-secondary); margin-top: 8px;">任务已在后台执行，请稍后在搜索或数据概览中查看结果。</p>
                </div>
            ` + logsDiv.innerHTML;
        } catch (error) {
            alert('触发失败: ' + error.message);
        } finally {
            btn.disabled = false;
            btn.innerHTML = '<i class="fa-solid fa-rocket"></i> 派出 Agent';
        }
    });

    // === 统计视图加载 ===
    async function loadStats() {
        const grid = document.getElementById('statsGrid');
        grid.innerHTML = '<div class="loading-spinner"><div class="spinner"></div></div>';
        
        try {
            const res = await fetch('/api/stats');
            const stats = await res.json();
            
            grid.innerHTML = `
                <div class="stat-card">
                    <div class="stat-value">${stats.total_papers}</div>
                    <div class="stat-label">文献总数</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value" style="color: #eab308;">${stats.favorited_papers}</div>
                    <div class="stat-label">已收藏</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value" style="color: var(--accent-secondary);">${stats.total_crawls}</div>
                    <div class="stat-label">爬虫执行次数</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value" style="color: #10b981;">${stats.total_searches}</div>
                    <div class="stat-label">智能检索次数</div>
                </div>
            `;
        } catch (error) {
            grid.innerHTML = `<p style="color: #ef4444;">加载失败: ${error.message}</p>`;
        }
    }

    // === 我的收藏加载 ===
    async function loadLibrary() {
        // 复用搜索结果容器，但在一个新的 section 中渲染
        // 为简化示例，这里就不额外展开，实际可以通过调用 /api/papers?favorited=true 实现
    }

    // === AI 对话逻辑 ===
    let currentChatMessages = [];
    const chatInput = document.getElementById('chatInput');
    const chatSendBtn = document.getElementById('chatSendBtn');
    const chatHistory = document.getElementById('chatHistory');

    // 简单 Markdown 解析器 (加粗和换行)
    function parseSimpleMarkdown(text) {
        if (!text) return '';
        let html = text.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
        html = html.replace(/\n/g, '<br>');
        return html;
    }

    // 滚动到底部
    function scrollToBottom() {
        chatHistory.scrollTop = chatHistory.scrollHeight;
    }

    // 渲染聊天记录
    function renderChatMessages() {
        // 清空除了初始欢迎语之外的全部气泡
        const initialWelcome = chatHistory.firstElementChild;
        chatHistory.innerHTML = '';
        if (initialWelcome) chatHistory.appendChild(initialWelcome);

        currentChatMessages.forEach(msg => {
            if (msg.role === 'system') return; // 不渲染 system prompt

            const bubble = document.createElement('div');
            bubble.classList.add('chat-bubble');

            if (msg.role === 'user') {
                bubble.classList.add('user-bubble');
                bubble.innerHTML = `<div class="bubble-content">${parseSimpleMarkdown(msg.content)}</div>`;
            } else if (msg.role === 'assistant') {
                if (msg.tool_calls && msg.tool_calls.length > 0) {
                    // 模型尝试调用工具的提示气泡
                    bubble.classList.add('tool-bubble');
                    const toolNames = msg.tool_calls.map(tc => tc.function.name).join(', ');
                    bubble.innerHTML = `
                        <div class="tool-content">
                            <i class="fa-solid fa-wrench"></i>
                            <span>Agent 正在调用内部工具: ${toolNames}...</span>
                        </div>
                    `;
                } else if (msg.content) {
                    // 正常的助手回复
                    bubble.classList.add('assistant-bubble');
                    bubble.innerHTML = `<div class="bubble-content">${parseSimpleMarkdown(msg.content)}</div>`;
                } else {
                    return; // 防止空状态
                }
            } else if (msg.role === 'tool') {
                bubble.classList.add('tool-bubble');
                bubble.innerHTML = `
                    <div class="tool-content" style="border-color: #10b981;">
                        <i class="fa-solid fa-check" style="color: #10b981;"></i>
                        <span>工具 [${msg.name}] 执行完毕</span>
                    </div>
                `;
            }
            chatHistory.appendChild(bubble);
        });
        scrollToBottom();
    }

    // 发送消息
    async function sendChatMessage() {
        const text = chatInput.value.trim();
        if (!text) return;

        // 构建本地消息追加
        currentChatMessages.push({ role: 'user', content: text });
        chatInput.value = '';
        chatInput.style.height = 'auto'; // reset height
        
        renderChatMessages();

        // 禁用输入并显示 Loading 气泡
        chatInput.disabled = true;
        chatSendBtn.disabled = true;

        const loadingBubble = document.createElement('div');
        loadingBubble.classList.add('chat-bubble', 'assistant-bubble');
        loadingBubble.id = 'chatLoadingBubble';
        loadingBubble.innerHTML = `
            <div class="bubble-content" style="padding: 10px 18px;">
                <div class="typing-indicator">
                    <span></span><span></span><span></span>
                </div>
            </div>
        `;
        chatHistory.appendChild(loadingBubble);
        scrollToBottom();

        try {
            const res = await fetch('/api/agent/chat', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ messages: currentChatMessages })
            });
            const data = await res.json();
            
            // 用后端返回的带有上下文和工具调用结果的 messages 覆盖当前数组
            if (data.messages) {
                currentChatMessages = data.messages;
            }
        } catch (error) {
            console.error('Chat error:', error);
            currentChatMessages.push({ role: 'assistant', content: `❌ 请求失败: ${error.message}` });
        } finally {
            chatInput.disabled = false;
            chatSendBtn.disabled = false;
            chatInput.focus();
            renderChatMessages(); // 重新渲染最终状态（移除 loading 气泡）
        }
    }

    chatSendBtn.addEventListener('click', sendChatMessage);
    
    chatInput.addEventListener('keypress', (e) => {
        // 回车发送，Shift+回车换行
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendChatMessage();
        }
    });

    // 自动调整文本框高度
    chatInput.addEventListener('input', function() {
        this.style.height = 'auto';
        this.style.height = (this.scrollHeight) + 'px';
    });

});
