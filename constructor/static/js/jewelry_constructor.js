(() => {
    const STORAGE_KEY = 'rucodel-jewelry-constructor-v6';
    const FIXED_PREVIEW_ZOOM = 1.58;
    const STONE_GAP_MM = 0.35;
    const CLASP_GAP_MM = 8;
    const imageCache = new Map();
    const previewState = {
        zoom: FIXED_PREVIEW_ZOOM,
        drag: {
            active: false,
            stoneUid: null,
            pointerId: null,
            point: null,
            hoverIndex: -1,
        },
    };

    function clamp(value, min, max) {
        return Math.max(min, Math.min(max, value));
    }

    function parseCatalog() {
        const node = document.getElementById('jewelry-catalog-data');
        if (!node) return { kinds: [], bases: [], lengths: [], stones: [], clasps: [] };
        try {
            return JSON.parse(node.textContent);
        } catch (error) {
            console.error('Не удалось прочитать каталог украшений', error);
            return { kinds: [], bases: [], lengths: [], stones: [], clasps: [] };
        }
    }
    function parseCopiedWorkData() {
        const node = document.getElementById('copied-jewelry-work-data');
        if (!node) return null;
        try {
            const parsed = JSON.parse(node.textContent);
            return parsed && typeof parsed === 'object' ? parsed : null;
        } catch (error) {
            console.warn('Не удалось прочитать скопированную работу', error);
            return null;
        }
    }

    function getStoredState() {
        try {
            return JSON.parse(localStorage.getItem(STORAGE_KEY) || '{}');
        } catch (error) {
            console.warn('Не удалось прочитать состояние конструктора украшений', error);
            return {};
        }
    }

    function saveState(updates) {
        const nextState = { ...getStoredState(), ...updates };
        delete nextState.userPhotoDataUrl;
        try {
            localStorage.setItem(STORAGE_KEY, JSON.stringify(nextState));
        } catch (error) {
            console.warn('Не удалось сохранить состояние конструктора украшений', error);
        }
    }

    function clearStoredPhoto() {
        const state = getStoredState();
        if ('userPhotoDataUrl' in state) {
            delete state.userPhotoDataUrl;
            try {
                localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
            } catch (error) {
                console.warn('Не удалось очистить фото пользователя в конструкторе украшений', error);
            }
        }
    }

    function uid() {
        return `${Date.now()}-${Math.random().toString(16).slice(2, 10)}`;
    }

    function sanitizeStoneEntries(entries) {
        if (!Array.isArray(entries)) return [];
        return entries
            .filter((entry) => entry && typeof entry === 'object' && entry.slug)
            .map((entry) => ({ uid: entry.uid || uid(), slug: entry.slug }));
    }

    function getStoredStoneMap(catalog, state = getStoredState()) {
        const emptyMap = Object.fromEntries((catalog?.kinds || []).map((item) => [item.code, []]));
        if (!state || typeof state !== 'object') return emptyMap;

        if (state.selectedStonesByKind && typeof state.selectedStonesByKind === 'object') {
            Object.keys(emptyMap).forEach((kindCode) => {
                emptyMap[kindCode] = sanitizeStoneEntries(state.selectedStonesByKind[kindCode]);
            });
            return emptyMap;
        }

        const fallbackKind = state.jewelryKind && emptyMap[state.jewelryKind] !== undefined
            ? state.jewelryKind
            : (catalog?.kinds?.[0]?.code || 'necklace');
        emptyMap[fallbackKind] = sanitizeStoneEntries(state.selectedStones);
        return emptyMap;
    }

    function loadImage(src) {
        if (!src) return Promise.reject(new Error('Пустой путь к изображению.'));
        if (imageCache.has(src)) {
            return imageCache.get(src);
        }
        const promise = new Promise((resolve, reject) => {
            const image = new Image();
            image.onload = () => resolve(image);
            image.onerror = () => reject(new Error(`Не удалось загрузить изображение ${src}`));
            image.src = src;
        });
        imageCache.set(src, promise);
        return promise;
    }

    function applyCopiedWorkState(catalog, copiedWork) {
        const selections = copiedWork?.selections || {};
        const jewelryKind = selections.jewelry_kind_code || currentKind(catalog);
        const baseCode = selections.base_code || catalog.bases.find((item) => item.kind === jewelryKind)?.code || catalog.bases[0]?.code || '';
        const targetLengthMm = Number(selections.target_length_mm || catalog.lengths.find((item) => item.kind === jewelryKind)?.value_mm || 0);
        const claspSlug = selections.clasp_slug || catalog.clasps[0]?.slug || '';
        const selectedStones = Array.isArray(selections.stones)
            ? selections.stones.map((stone) => ({ uid: uid(), slug: stone.slug })).filter((stone) => stone.slug)
            : [];
        const selectedStonesByKind = getStoredStoneMap(catalog, {});
        selectedStonesByKind[jewelryKind] = selectedStones;
        saveState({ jewelryKind, baseCode, targetLengthMm, claspSlug, selectedStones, selectedStonesByKind });
    }

    function setSelectedCardStyles() {
        const groups = [
            ['input[name="jewelry_kind"]', '.jewelry-kind-card'],
            ['input[name="jewelry_base"]', '.jewelry-base-card'],
            ['input[name="target_length"]', '.length-choice-card'],
            ['input[name="clasp_type"]', '.clasp-choice-card'],
        ];
        groups.forEach(([inputSelector, cardSelector]) => {
            document.querySelectorAll(cardSelector).forEach((card) => {
                const input = card.querySelector(inputSelector);
                const checked = Boolean(input?.checked) && !card.classList.contains('hidden');
                card.classList.toggle('border-slate-900', checked);
                card.classList.toggle('ring-2', checked);
                card.classList.toggle('ring-slate-900/10', checked);
                card.classList.toggle('bg-slate-50', checked);
            });
        });
    }

    function restoreState(catalog) {
        const state = getStoredState();
        if (state.jewelryKind) {
            const input = Array.from(document.querySelectorAll('input[name="jewelry_kind"]')).find((item) => item.value === state.jewelryKind);
            if (input) input.checked = true;
        }
        if (state.baseCode) {
            const input = Array.from(document.querySelectorAll('input[name="jewelry_base"]')).find((item) => item.value === state.baseCode);
            if (input) input.checked = true;
        }
        if (state.targetLengthMm) {
            const input = Array.from(document.querySelectorAll('input[name="target_length"]')).find((item) => Number(item.value) === Number(state.targetLengthMm));
            if (input) input.checked = true;
        }
        if (state.claspSlug) {
            const input = Array.from(document.querySelectorAll('input[name="clasp_type"]')).find((item) => item.value === state.claspSlug);
            if (input) input.checked = true;
        }
        previewState.zoom = FIXED_PREVIEW_ZOOM;
        updateZoomLabel();
        syncVisibleControls(catalog);
    }

    function currentKind(catalog) {
        return document.querySelector('input[name="jewelry_kind"]:checked')?.value || catalog.kinds[0]?.code || 'necklace';
    }

    function syncVisibleControls(catalog) {
        const kind = currentKind(catalog);

        let firstBaseInput = null;
        document.querySelectorAll('.jewelry-base-card').forEach((card) => {
            const input = card.querySelector('input[name="jewelry_base"]');
            const matches = input?.dataset.kind === kind;
            card.classList.toggle('hidden', !matches);
            if (matches && !firstBaseInput) firstBaseInput = input;
        });
        const checkedBase = Array.from(document.querySelectorAll('input[name="jewelry_base"]')).find((input) => input.checked && !input.closest('.hidden'));
        if (!checkedBase && firstBaseInput) {
            firstBaseInput.checked = true;
        }

        let firstLengthInput = null;
        document.querySelectorAll('.length-choice-card').forEach((card) => {
            const input = card.querySelector('input[name="target_length"]');
            const matches = input?.dataset.kind === kind;
            card.classList.toggle('hidden', !matches);
            if (matches && !firstLengthInput) firstLengthInput = input;
        });
        const checkedLength = Array.from(document.querySelectorAll('input[name="target_length"]')).find((input) => input.checked && !input.closest('.hidden'));
        if (!checkedLength && firstLengthInput) {
            firstLengthInput.checked = true;
        }

        const claspSection = document.getElementById('clasp-section');
        if (claspSection) {
            claspSection.classList.toggle('hidden', kind === 'earrings');
        }
        if (kind === 'earrings') {
            const claspInput = Array.from(document.querySelectorAll('input[name="clasp_type"]')).find((input) => input.checked);
            if (!claspInput) {
                const firstClasp = document.querySelector('input[name="clasp_type"]');
                if (firstClasp) firstClasp.checked = true;
            }
        }

        const heading = document.getElementById('jewelry-size-heading');
        if (heading) {
            heading.textContent = kind === 'earrings' ? 'Высота' : kind === 'bracelet' ? 'Размер' : 'Длина';
        }

        const kindBadge = document.getElementById('jewelry-kind-badge');
        const kindConfig = catalog.kinds.find((item) => item.code === kind);
        if (kindBadge) {
            kindBadge.textContent = kindConfig?.name || 'Украшение';
        }

        const photoHint = document.getElementById('jewelry-photo-hint');
        if (photoHint) {
            photoHint.textContent = kindConfig?.photo_hint || 'Загрузите подходящее фото для примерки.';
        }

        const userTitle = document.getElementById('jewelry-user-title');
        const resultTitle = document.getElementById('jewelry-result-title');
        const uploadLabelText = document.getElementById('jewelry-upload-label-text');
        if (kind === 'bracelet') {
            if (userTitle) userTitle.textContent = 'Фото руки пользователя';
            if (resultTitle) resultTitle.textContent = 'Фото руки с браслетом';
            if (uploadLabelText) uploadLabelText.textContent = 'Загрузить фото руки';
        } else if (kind === 'earrings') {
            if (userTitle) userTitle.textContent = 'Фото пользователя';
            if (resultTitle) resultTitle.textContent = 'Фото с серьгами';
            if (uploadLabelText) uploadLabelText.textContent = 'Загрузить фото';
        } else {
            if (userTitle) userTitle.textContent = 'Фото пользователя';
            if (resultTitle) resultTitle.textContent = 'Фото с украшением';
            if (uploadLabelText) uploadLabelText.textContent = 'Загрузить фото';
        }

        const viewHint = document.getElementById('jewelry-view-hint');
        if (viewHint) {
            viewHint.textContent = kind === 'earrings'
                ? 'В превью показана парная сборка. Любой перенос элемента автоматически зеркалится на вторую серьгу.'
                : kind === 'bracelet'
                    ? 'Размер влияет на посадку браслета.'
                    : 'Длина меняет посадку украшения.';
        }
    }

    function getSelectionState(catalog) {
        const state = getStoredState();
        const jewelryKind = currentKind(catalog);
        const visibleBase = Array.from(document.querySelectorAll('input[name="jewelry_base"]')).find((input) => input.checked && !input.closest('.hidden'));
        const visibleLength = Array.from(document.querySelectorAll('input[name="target_length"]')).find((input) => input.checked && !input.closest('.hidden'));
        const claspInput = document.querySelector('input[name="clasp_type"]:checked');
        const defaultBase = catalog.bases.find((item) => item.kind === jewelryKind);
        const defaultLength = catalog.lengths.find((item) => item.kind === jewelryKind);
        const selectedStonesByKind = getStoredStoneMap(catalog, state);
        return {
            jewelryKind,
            baseCode: visibleBase?.value || defaultBase?.code || '',
            targetLengthMm: Number(visibleLength?.value || defaultLength?.value_mm || 0),
            claspSlug: jewelryKind === 'earrings' ? '' : (claspInput?.value || catalog.clasps[0]?.slug || ''),
            selectedStones: selectedStonesByKind[jewelryKind] || [],
            selectedStonesByKind,
        };
    }

    function buildSelectedStoneDetails(catalog, selectedStones) {
        return selectedStones
            .map((entry) => {
                const stone = catalog.stones.find((item) => item.slug === entry.slug);
                if (!stone) return null;
                return {
                    uid: entry.uid,
                    slug: stone.slug,
                    name: stone.name,
                    diameter_mm: Number(stone.diameter_mm || 0),
                    occupied_length_mm: Number(stone.occupied_length_mm || stone.diameter_mm || 0),
                    color_hex: stone.color_hex,
                    material: stone.material,
                    preview_asset_url: stone.preview_asset_url,
                };
            })
            .filter(Boolean);
    }

    function summarize(catalog) {
        const state = getSelectionState(catalog);
        const kind = catalog.kinds.find((item) => item.code === state.jewelryKind) || catalog.kinds[0];
        const base = catalog.bases.find((item) => item.code === state.baseCode) || catalog.bases.find((item) => item.kind === state.jewelryKind) || catalog.bases[0];
        const length = catalog.lengths.find((item) => Number(item.value_mm) === Number(state.targetLengthMm) && item.kind === state.jewelryKind)
            || catalog.lengths.find((item) => item.kind === state.jewelryKind)
            || catalog.lengths[0];
        const clasp = state.jewelryKind === 'earrings'
            ? null
            : (catalog.clasps.find((item) => item.slug === state.claspSlug) || catalog.clasps[0] || null);
        const stones = buildSelectedStoneDetails(catalog, state.selectedStones);
        const stonesLength = stones.reduce((sum, stone) => sum + Number(stone.occupied_length_mm || stone.diameter_mm || 0), 0);
        const gapLength = Math.max(0, stones.length - 1) * STONE_GAP_MM;
        const claspLength = clasp ? Number(clasp.visual_length_mm || 0) : 0;
        const usedLength = stonesLength + gapLength + claspLength;
        const stoneSummary = stones.length
            ? stones.map((stone) => `${stone.name} ${stone.diameter_mm} мм`).join(', ')
            : 'без камней';
        const summaryText = [kind?.name, base?.name, length?.label, clasp?.name, stoneSummary].filter(Boolean).join(' · ');

        return {
            kind,
            base,
            length,
            clasp,
            stones,
            usedLengthMm: Number(usedLength.toFixed(1)),
            summary: summaryText,
            selections: {
                jewelry_kind: kind?.name || '',
                jewelry_kind_code: kind?.code || '',
                base: base?.name || '',
                base_code: base?.code || '',
                target_length: length?.label || '',
                target_length_mm: Number(length?.value_mm || 0),
                clasp: clasp?.name || '',
                clasp_slug: clasp?.slug || '',
                used_length_mm: Number(usedLength.toFixed(1)),
                stones: stones.map((stone) => ({
                    slug: stone.slug,
                    name: stone.name,
                    diameter_mm: stone.diameter_mm,
                    occupied_length_mm: stone.occupied_length_mm,
                    material: stone.material,
                })),
            },
        };
    }

    function filterCatalogCards() {
        const query = String(document.getElementById('stone-search-input')?.value || '').trim().toLowerCase();
        document.querySelectorAll('.stone-catalog-card').forEach((card) => {
            const haystack = String(card.dataset.stoneSearch || '');
            const visible = !query || haystack.includes(query);
            card.classList.toggle('hidden', !visible);
        });
    }

    function renderSelectedStonesList(catalog) {
        const container = document.getElementById('selected-stones-list');
        if (!container) return;

        const summary = summarize(catalog);
        const stones = summary.stones;
        const countBadge = document.getElementById('selected-stones-count');
        if (countBadge) {
            countBadge.textContent = `${stones.length} шт.`;
        }

        if (!stones.length) {
            container.innerHTML = `
                <div class="min-w-full rounded-2xl border border-dashed border-slate-200 bg-white px-4 py-6 text-center text-sm text-slate-500">
                    Добавьте камушки из каталога слева — последовательность появится здесь.
                </div>
            `;
            bindSequenceScroller(container);
            return;
        }

        container.innerHTML = stones.map((stone, index) => `
            <div class="w-full rounded-2xl border border-slate-200 bg-white px-3 py-3 transition shadow-sm" data-stone-item data-stone-uid="${stone.uid}">
                <div class="flex items-start gap-3">
                    <div class="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-slate-900 text-[11px] font-semibold text-white">${index + 1}</div>
                    <div class="h-10 w-10 shrink-0 rounded-xl border border-slate-200 bg-slate-50 p-1.5 flex items-center justify-center">
                        <img src="${stone.preview_asset_url}" alt="${stone.name}" class="max-h-full object-contain">
                    </div>
                    <div class="min-w-0 flex-1">
                        <div class="truncate text-sm font-semibold text-slate-800">${stone.name}</div>
                        <div class="mt-0.5 text-[11px] text-slate-500">${stone.material} · ${stone.diameter_mm} мм</div>
                    </div>
                </div>
                <div class="mt-3 flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
                    <span class="text-[11px] text-slate-500">Порядок меняется в превью</span>
                    <button type="button" class="stone-remove-btn inline-flex w-full items-center justify-center rounded-full border border-rose-200 px-2.5 py-1.5 text-[11px] font-medium text-rose-600 sm:w-auto" data-stone-uid="${stone.uid}">Удалить</button>
                </div>
            </div>
        `).join('');

        container.querySelectorAll('.stone-remove-btn').forEach((button) => {
            button.addEventListener('click', () => removeStone(button.dataset.stoneUid, catalog));
        });
        bindSequenceScroller(container);
    }

    function bindSequenceScroller(container) {
        if (!container || container.dataset.sequenceScrollerBound === 'true') return;
        container.dataset.sequenceScrollerBound = 'true';
    }


function canAddStone(stoneSlug, catalog) {
    const summary = summarize(catalog);
    const target = Number(summary.length?.value_mm || 0);
    if (!target) return true;
    const stone = catalog.stones.find((item) => item.slug === stoneSlug);
    if (!stone) return false;
    const extraGap = summary.stones.length > 0 ? STONE_GAP_MM : 0;
    const extraLength = Number(stone.occupied_length_mm || stone.diameter_mm || 0) + extraGap;
    return (Number(summary.usedLengthMm || 0) + extraLength) <= target + 0.001;
}

function syncStoneAvailability(catalog) {
    document.querySelectorAll('.add-stone-btn').forEach((button) => {
        const allowed = canAddStone(button.dataset.stoneSlug, catalog);
        button.disabled = !allowed;
        button.classList.toggle('opacity-50', !allowed);
        button.classList.toggle('cursor-not-allowed', !allowed);
        button.classList.toggle('bg-slate-900', allowed);
        button.classList.toggle('bg-slate-300', !allowed);
        button.classList.toggle('hover:bg-slate-700', allowed);
        button.title = allowed ? '' : 'Длина основы уже достигнута';
    });
}

    function persistSelectedStones(catalog, selectedStones) {
        const state = getSelectionState(catalog);
        const selectedStonesByKind = { ...(state.selectedStonesByKind || {}) };
        selectedStonesByKind[state.jewelryKind] = sanitizeStoneEntries(selectedStones);
        saveState({
            selectedStones: selectedStonesByKind[state.jewelryKind],
            selectedStonesByKind,
        });
    }

    function addStone(stoneSlug, catalog) {
        if (!canAddStone(stoneSlug, catalog)) {
            const warning = document.getElementById('jewelry-overflow-warning');
            if (warning) {
                warning.textContent = 'Достигнута выбранная длина основы. Новые камушки больше не добавляются.';
            }
            syncStoneAvailability(catalog);
            return;
        }
        const state = getSelectionState(catalog);
        const nextStones = [...state.selectedStones, { uid: uid(), slug: stoneSlug }];
        persistSelectedStones(catalog, nextStones);
        rerender(catalog);
    }

    function removeStone(stoneUid, catalog) {
        const state = getSelectionState(catalog);
        const nextStones = state.selectedStones.filter((entry) => entry.uid !== stoneUid);
        persistSelectedStones(catalog, nextStones);
        rerender(catalog);
    }

    function moveStone(stoneUid, direction, catalog) {
        const state = getSelectionState(catalog);
        const index = state.selectedStones.findIndex((entry) => entry.uid === stoneUid);
        if (index < 0) return;
        const targetIndex = direction === 'up' ? index - 1 : index + 1;
        if (targetIndex < 0 || targetIndex >= state.selectedStones.length) return;
        const swapped = [...state.selectedStones];
        [swapped[index], swapped[targetIndex]] = [swapped[targetIndex], swapped[index]];
        persistSelectedStones(catalog, swapped);
        rerender(catalog);
    }

    function moveStoneToIndex(stoneUid, targetIndex, catalog) {
        const state = getSelectionState(catalog);
        const currentIndex = state.selectedStones.findIndex((entry) => entry.uid === stoneUid);
        if (currentIndex < 0 || targetIndex < 0) return;

        const reordered = [...state.selectedStones];
        const [moved] = reordered.splice(currentIndex, 1);
        let adjustedTarget = targetIndex;
        if (currentIndex < targetIndex) adjustedTarget -= 1;
        adjustedTarget = Math.max(0, Math.min(adjustedTarget, reordered.length));
        reordered.splice(adjustedTarget, 0, moved);
        persistSelectedStones(catalog, reordered);
        rerender(catalog);
    }

    function clearStones(catalog) {
        persistSelectedStones(catalog, []);
        rerender(catalog);
    }

    function bindListDragAndDrop(container, catalog) {
        let draggedUid = null;
        container.querySelectorAll('[data-stone-item]').forEach((item) => {
            item.addEventListener('dragstart', (event) => {
                draggedUid = item.dataset.stoneUid || null;
                item.classList.add('opacity-60');
                if (event.dataTransfer) {
                    event.dataTransfer.effectAllowed = 'move';
                    event.dataTransfer.setData('text/plain', draggedUid || '');
                }
            });

            item.addEventListener('dragend', () => {
                draggedUid = null;
                container.querySelectorAll('[data-stone-item]').forEach((node) => {
                    node.classList.remove('opacity-60', 'ring-2', 'ring-brand-200', 'border-brand-300');
                });
            });

            item.addEventListener('dragover', (event) => {
                event.preventDefault();
                item.classList.add('ring-2', 'ring-brand-200', 'border-brand-300');
            });

            item.addEventListener('dragleave', () => {
                item.classList.remove('ring-2', 'ring-brand-200', 'border-brand-300');
            });

            item.addEventListener('drop', (event) => {
                event.preventDefault();
                item.classList.remove('ring-2', 'ring-brand-200', 'border-brand-300');
                const dropUid = item.dataset.stoneUid;
                if (!draggedUid || !dropUid || draggedUid === dropUid) return;

                const items = Array.from(container.querySelectorAll('[data-stone-item]'));
                const targetIndex = items.findIndex((node) => node.dataset.stoneUid === dropUid);
                const rect = item.getBoundingClientRect();
                const insertAfter = event.clientY > rect.top + rect.height / 2;
                moveStoneToIndex(draggedUid, insertAfter ? targetIndex + 1 : targetIndex, catalog);
            });
        });
    }

    function updateZoomLabel() {
        const label = document.getElementById('jewelry-zoom-value');
        if (label) {
            label.textContent = 'фиксировано';
        }
    }

    function updateSummaryUi(summary) {
        const badge = document.getElementById('jewelry-length-badge');
        if (badge) {
            const target = Number(summary.length?.value_mm || 0);
            badge.textContent = `${summary.usedLengthMm} / ${target} мм`;
            const atLimit = summary.usedLengthMm >= target - 0.001 && summary.kind?.code !== 'earrings';
            badge.classList.toggle('text-amber-700', atLimit);
            badge.classList.toggle('border-amber-200', atLimit);
            badge.classList.toggle('bg-amber-50', atLimit);
        }
        const warning = document.getElementById('jewelry-overflow-warning');
        if (warning) {
            const target = Number(summary.length?.value_mm || 0);
            warning.textContent = summary.usedLengthMm >= target - 0.001 && summary.kind?.code !== 'earrings'
                ? 'Достигнута выбранная длина основы. Чтобы добавить новый элемент, сначала удалите один из текущих.'
                : '';
        }
        const summaryEl = document.getElementById('jewelry-choice-summary');
        if (summaryEl) {
            summaryEl.textContent = summary.summary;
        }
    }

    function drawBead(ctx, stone, x, y, radius, options = {}) {
        const floating = Boolean(options.floating);
        if (floating) {
            ctx.save();
            ctx.shadowColor = 'rgba(15, 23, 42, 0.24)';
            ctx.shadowBlur = 18;
            ctx.shadowOffsetY = 10;
        }
        const gradient = ctx.createRadialGradient(x - radius * 0.38, y - radius * 0.38, radius * 0.16, x, y, radius);
        gradient.addColorStop(0, 'rgba(255,255,255,0.96)');
        gradient.addColorStop(0.22, stone.color_hex || '#d7dee8');
        gradient.addColorStop(0.82, stone.color_hex || '#d7dee8');
        gradient.addColorStop(1, 'rgba(15,23,42,0.28)');
        ctx.fillStyle = gradient;
        ctx.beginPath();
        ctx.arc(x, y, radius, 0, Math.PI * 2);
        ctx.fill();

        ctx.strokeStyle = floating ? 'rgba(255,255,255,0.74)' : 'rgba(255,255,255,0.56)';
        ctx.lineWidth = Math.max(1, radius * 0.1);
        ctx.beginPath();
        ctx.arc(x, y, radius - ctx.lineWidth, Math.PI * 1.08, Math.PI * 1.82);
        ctx.stroke();
        if (floating) ctx.restore();
    }

    function mapMmToPx(summary, totalPathPx) {
        const target = Number(summary.length?.value_mm || 0);
        return target > 0 ? totalPathPx / target : 2.2;
    }

    function cubicBezierPoint(p0, p1, p2, p3, t) {
        const inv = 1 - t;
        return {
            x: (p0.x * inv ** 3) + (3 * p1.x * inv ** 2 * t) + (3 * p2.x * inv * t * t) + (p3.x * t ** 3),
            y: (p0.y * inv ** 3) + (3 * p1.y * inv ** 2 * t) + (3 * p2.y * inv * t * t) + (p3.y * t ** 3),
        };
    }

    function approximateBezierLength(p0, p1, p2, p3, steps = 28) {
        let length = 0;
        let previous = p0;
        for (let step = 1; step <= steps; step += 1) {
            const point = cubicBezierPoint(p0, p1, p2, p3, step / steps);
            length += Math.hypot(point.x - previous.x, point.y - previous.y);
            previous = point;
        }
        return length;
    }

    function buildNecklaceLayout(summary, width, height, zoom) {
        const zoomScale = clamp(Number(zoom || 1.2), 0.7, 2.8);
        const targetLength = Number(summary.length?.value_mm || 420);
        const sizeNorm = clamp((targetLength - 360) / 160, 0, 1);
        const zoomNorm = zoomScale - 1;
        const centerX = width / 2;
        const shoulderSpan = width * (0.50 + zoomNorm * 0.12);
        const leftX = centerX - shoulderSpan / 2;
        const rightX = centerX + shoulderSpan / 2;
        const topY = height * (0.17 - zoomNorm * 0.038);
        const sagDepth = height * (0.17 + sizeNorm * 0.24) * (0.96 + zoomNorm * 0.18);
        const controlInset = shoulderSpan * (0.16 - sizeNorm * 0.02);
        const controlLeftX = leftX + controlInset;
        const controlRightX = rightX - controlInset;
        const controlY = topY + sagDepth;
        const p0 = { x: leftX, y: topY };
        const p1 = { x: controlLeftX, y: controlY };
        const p2 = { x: controlRightX, y: controlY };
        const p3 = { x: rightX, y: topY };
        const pathLengthPx = approximateBezierLength(p0, p1, p2, p3, 40);
        const pxPerMm = mapMmToPx(summary, pathLengthPx);
        const claspPadMm = summary.clasp ? Number(summary.clasp.visual_length_mm || 0) * 0.54 : 0;
        const used = Math.max(0, Math.min(Number(summary.usedLengthMm || 0), Number(summary.length?.value_mm || summary.usedLengthMm || 0)));
        let progressMm = Math.max(0, ((targetLength - used) / 2)) + claspPadMm;
        const stones = [];
        const hitPoints = [];

        summary.stones.forEach((stone, index) => {
            const occupiedMm = Number(stone.occupied_length_mm || stone.diameter_mm || 0);
            const centerMm = progressMm + occupiedMm / 2;
            const t = targetLength > 0 ? centerMm / targetLength : 0.5;
            const point = cubicBezierPoint(p0, p1, p2, p3, t);
            const radius = Math.max(7.5, Math.min(34, (stone.diameter_mm * pxPerMm * (0.72 + zoomScale * 0.18)) / 2));
            const item = { ...stone, x: point.x, y: point.y, radius, orderMetric: t, index };
            stones.push(item);
            hitPoints.push({ ...item, isPrimary: true });
            progressMm += occupiedMm + STONE_GAP_MM;
        });

        return {
            kind: 'necklace',
            centerX,
            centerY: topY + sagDepth * 0.52,
            leftX,
            rightX,
            topY,
            controlLeftX,
            controlRightX,
            controlY,
            stones,
            hitPoints,
            primaryPoints: stones,
            claspLeft: { x: leftX - 4, y: topY + 1, angle: -0.08 },
            claspRight: { x: rightX + 4, y: topY + 1, angle: 0.08 },
        };
    }

    function buildBraceletLayout(summary, width, height, zoom) {
        const zoomScale = clamp(Number(zoom || 1.2), 0.7, 2.8);
        const sizeNorm = clamp((Number(summary.length?.value_mm || 180) - 160) / 60, 0, 1);
        const visualScale = 0.92 + (zoomScale - 0.7) * 0.58;
        const centerX = width / 2;
        const centerY = height * 0.52;
        const desiredRadiusX = width * (0.13 + sizeNorm * 0.15) * visualScale;
        const desiredRadiusY = height * (0.108 + sizeNorm * 0.138) * visualScale;
        const safeMarginX = Math.max(38, width * 0.065);
        const safeMarginTop = Math.max(42, height * 0.085);
        const safeMarginBottom = Math.max(54, height * 0.11);
        const radiusX = Math.min(desiredRadiusX, (width / 2) - safeMarginX);
        const radiusY = Math.min(desiredRadiusY, centerY - safeMarginTop, height - centerY - safeMarginBottom);
        const gapAngle = 0.56;
        const startAngle = Math.PI + gapAngle / 2;
        const endAngle = Math.PI * 3 - gapAngle / 2;
        const pathSpan = endAngle - startAngle;
        const approxPathPx = ((radiusX + radiusY) * Math.PI) - (radiusX + radiusY) * gapAngle * 0.42;
        const pxPerMm = mapMmToPx(summary, approxPathPx);
        const claspPadMm = summary.clasp ? Number(summary.clasp.visual_length_mm || 0) * 0.6 : 0;
        const targetLength = Number(summary.length?.value_mm || 0);
        const used = Math.max(0, Math.min(Number(summary.usedLengthMm || 0), Number(summary.length?.value_mm || summary.usedLengthMm || 0)));
        let progressMm = Math.max(0, ((targetLength - used) / 2)) + claspPadMm;
        const stones = [];
        const hitPoints = [];
        summary.stones.forEach((stone, index) => {
            const occupiedMm = Number(stone.occupied_length_mm || stone.diameter_mm || 0);
            const centerMm = progressMm + occupiedMm / 2;
            const t = targetLength > 0 ? centerMm / targetLength : 0.5;
            const angle = startAngle + pathSpan * t;
            const x = centerX + Math.cos(angle) * radiusX;
            const y = centerY + Math.sin(angle) * radiusY;
            const radius = Math.max(7.5, Math.min(30, (stone.diameter_mm * pxPerMm * (0.76 + zoomScale * 0.20)) / 2));
            const item = { ...stone, x, y, radius, orderMetric: t, angle, index };
            stones.push(item);
            hitPoints.push({ ...item, isPrimary: true });
            progressMm += occupiedMm + STONE_GAP_MM;
        });
        const leftPoint = { x: centerX + Math.cos(startAngle) * radiusX, y: centerY + Math.sin(startAngle) * radiusY };
        const rightPoint = { x: centerX + Math.cos(endAngle) * radiusX, y: centerY + Math.sin(endAngle) * radiusY };
        return {
            kind: 'bracelet',
            centerX,
            centerY,
            radiusX,
            radiusY,
            startAngle,
            endAngle,
            stones,
            hitPoints,
            primaryPoints: stones,
            claspLeft: { x: leftPoint.x + 3, y: leftPoint.y + 1, angle: -0.12 },
            claspRight: { x: rightPoint.x - 3, y: rightPoint.y + 1, angle: 0.12 },
        };
    }

    function buildEarringsLayout(summary, width, height, zoom) {
        const zoomScale = clamp(Number(zoom || 1.2), 0.7, 2.8);
        const sizeNorm = clamp((Number(summary.length?.value_mm || 55) - 40) / 30, 0, 1);
        const visualScale = 0.84 + (zoomScale - 0.7) * 0.78;
        const leftX = width * 0.33;
        const rightX = width * 0.67;
        const topY = height * (0.18 - (zoomScale - 1) * 0.04);
        const dropHeight = height * (0.10 + sizeNorm * 0.34) * visualScale;
        const pathLengthPx = dropHeight;
        const pxPerMm = mapMmToPx(summary, pathLengthPx);
        const targetLength = Number(summary.length?.value_mm || 0);
        const used = Math.max(0, Math.min(Number(summary.usedLengthMm || 0), Number(summary.length?.value_mm || summary.usedLengthMm || 0)));
        let progressMm = Math.max(0, ((targetLength - used) / 2));
        const stones = [];
        const hitPoints = [];
        summary.stones.forEach((stone, index) => {
            const occupiedMm = Number(stone.occupied_length_mm || stone.diameter_mm || 0);
            const centerMm = progressMm + occupiedMm / 2;
            const t = targetLength > 0 ? centerMm / targetLength : 0.5;
            const y = topY + 44 + dropHeight * t;
            const radius = Math.max(7, Math.min(28, (stone.diameter_mm * pxPerMm * (0.88 + zoomScale * 0.18)) / 2));
            const item = { ...stone, x: leftX, y, radius, orderMetric: t, index };
            stones.push(item);
            hitPoints.push({ ...item, x: leftX, isPrimary: true });
            hitPoints.push({ ...item, x: rightX, isPrimary: false });
            progressMm += occupiedMm + STONE_GAP_MM;
        });
        return {
            kind: 'earrings',
            leftX,
            rightX,
            topY,
            dropHeight,
            stones,
            hitPoints,
            primaryPoints: stones,
        };
    }

    function buildPreviewLayout(summary, width, height, zoom) {
        if (summary.kind?.code === 'bracelet') return buildBraceletLayout(summary, width, height, zoom);
        if (summary.kind?.code === 'earrings') return buildEarringsLayout(summary, width, height, zoom);
        return buildNecklaceLayout(summary, width, height, zoom);
    }

    async function drawClaspIcons(ctx, summary, layout) {
        if (!summary.clasp?.preview_asset_url || summary.kind?.code === 'earrings') return;
        try {
            const claspImage = await loadImage(summary.clasp.preview_asset_url);
            const anchors = [layout.claspLeft, layout.claspRight].filter(Boolean);
            const iconSize = summary.kind?.code === 'bracelet' ? 18 : 24;
            anchors.forEach((anchor, index) => {
                ctx.save();
                ctx.translate(anchor.x, anchor.y);
                ctx.rotate(Number(anchor.angle || 0));
                if (summary.kind?.code === 'bracelet' && index === 1) {
                    ctx.scale(-1, 1);
                }
                ctx.drawImage(claspImage, -iconSize / 2, -iconSize / 2, iconSize, iconSize);
                ctx.restore();
            });
        } catch (error) {
            console.warn(error);
        }
    }

    function drawEarringHardware(ctx, summary, layout) {
        ctx.strokeStyle = summary.base?.stroke || '#8b949e';
        ctx.lineWidth = 2.4;
        const style = summary.base?.render_style || 'hook';
        [layout.leftX, layout.rightX].forEach((x) => {
            if (style === 'stud') {
                ctx.fillStyle = '#d5dbe5';
                ctx.beginPath();
                ctx.arc(x, layout.topY + 6, 7, 0, Math.PI * 2);
                ctx.fill();
                ctx.beginPath();
                ctx.moveTo(x, layout.topY + 12);
                ctx.lineTo(x, layout.topY + 36);
                ctx.stroke();
            } else if (style === 'hoop') {
                ctx.beginPath();
                ctx.arc(x, layout.topY + 16, 13, Math.PI * 0.15, Math.PI * 1.85);
                ctx.stroke();
                ctx.beginPath();
                ctx.moveTo(x, layout.topY + 29);
                ctx.lineTo(x, layout.topY + 40);
                ctx.stroke();
            } else {
                ctx.beginPath();
                ctx.moveTo(x, layout.topY + 2);
                ctx.bezierCurveTo(x - 10, layout.topY + 2, x - 12, layout.topY + 26, x, layout.topY + 30);
                ctx.stroke();
                ctx.beginPath();
                ctx.moveTo(x, layout.topY + 30);
                ctx.lineTo(x, layout.topY + 42);
                ctx.stroke();
            }
        });
    }

    async function renderJewelryPreview(catalog) {
        const canvas = document.getElementById('jewelry-preview-canvas');
        if (!canvas) return;
        const ctx = canvas.getContext('2d');
        const dpr = Math.min(window.devicePixelRatio || 1, 2);
        const width = canvas.clientWidth || 860;
        const height = canvas.clientHeight || 640;
        canvas.width = Math.max(1, Math.floor(width * dpr));
        canvas.height = Math.max(1, Math.floor(height * dpr));
        ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
        ctx.clearRect(0, 0, width, height);

        const summary = summarize(catalog);
        const layout = buildPreviewLayout(summary, width, height, previewState.zoom);
        const dragState = previewState.drag;
        const draggedUid = dragState.active ? dragState.stoneUid : null;

        ctx.lineCap = 'round';
        ctx.strokeStyle = summary.base?.stroke || '#8b8fa1';
        ctx.lineWidth = Math.max(2, Number(summary.base?.line_width || 3) * (0.92 + (previewState.zoom - 1) * 0.45));

        if (summary.kind?.code === 'necklace') {
            ctx.beginPath();
            ctx.moveTo(layout.leftX, layout.topY);
            ctx.bezierCurveTo(layout.controlLeftX, layout.controlY, layout.controlRightX, layout.controlY, layout.rightX, layout.topY);
            ctx.stroke();
        } else if (summary.kind?.code === 'bracelet') {
            ctx.beginPath();
            ctx.ellipse(layout.centerX, layout.centerY, layout.radiusX, layout.radiusY, 0, layout.startAngle, layout.endAngle);
            ctx.stroke();
        } else {
            drawEarringHardware(ctx, summary, layout);
            [layout.leftX, layout.rightX].forEach((x) => {
                ctx.beginPath();
                ctx.moveTo(x, layout.topY + 42);
                ctx.lineTo(x, layout.topY + layout.dropHeight + 42);
                ctx.stroke();
            });
        }

        const normalStones = summary.kind?.code === 'earrings'
            ? layout.hitPoints.filter((stone) => !draggedUid || stone.uid !== draggedUid)
            : layout.stones.filter((stone) => !draggedUid || stone.uid !== draggedUid);
        normalStones.forEach((stone) => drawBead(ctx, stone, stone.x, stone.y, stone.radius));

        await drawClaspIcons(ctx, summary, layout);

        if (draggedUid && dragState.point) {
            const draggedStone = layout.primaryPoints.find((stone) => stone.uid === draggedUid);
            if (draggedStone) {
                drawBead(ctx, draggedStone, dragState.point.x, dragState.point.y - 16, draggedStone.radius * 1.08, { floating: true });
            }
        }

        canvas._previewLayout = layout;
        updateSummaryUi(summary);
    }

    function getCanvasPoint(canvas, event) {
        const rect = canvas.getBoundingClientRect();
        return {
            x: event.clientX - rect.left,
            y: event.clientY - rect.top,
        };
    }

    function findStoneAtPoint(hitPoints, point) {
        return [...hitPoints].reverse().find((stone) => {
            const dx = point.x - stone.x;
            const dy = point.y - stone.y;
            return (dx * dx) + (dy * dy) <= (stone.radius + 14) ** 2;
        }) || null;
    }

    function getPointMetric(kind, point, layout) {
        if (kind === 'bracelet') {
            const angle = Math.atan2(point.y - layout.centerY, point.x - layout.centerX);
            let normalized = angle;
            if (normalized < layout.startAngle) normalized += Math.PI * 2;
            return normalized;
        }
        if (kind === 'earrings') return point.y;
        return point.x;
    }

    function getPreviewTargetIndex(layout, draggedUid, point) {
        const primary = layout.primaryPoints.filter((stone) => stone.uid !== draggedUid);
        if (!primary.length) return 0;
        const pointMetric = getPointMetric(layout.kind, point, layout);
        const sorted = [...primary].sort((a, b) => a.orderMetric - b.orderMetric);
        for (let index = 0; index < sorted.length; index += 1) {
            const stone = sorted[index];
            const metric = layout.kind === 'bracelet' ? stone.angle : (layout.kind === 'earrings' ? stone.y : stone.x);
            if (pointMetric < metric) return index;
        }
        return sorted.length;
    }

    function bindPreviewDrag(catalog) {
        const canvas = document.getElementById('jewelry-preview-canvas');
        if (!canvas || canvas.dataset.dragBound === 'true') return;
        canvas.dataset.dragBound = 'true';

        const dragState = previewState.drag;
        const resetCursor = () => {
            canvas.classList.remove('cursor-grabbing', 'cursor-default');
            canvas.classList.add('cursor-grab');
        };

        canvas.addEventListener('pointerdown', async (event) => {
            const layout = canvas._previewLayout;
            if (!layout) return;
            const point = getCanvasPoint(canvas, event);
            const hitStone = findStoneAtPoint(layout.hitPoints, point);
            if (!hitStone) return;
            dragState.active = true;
            dragState.stoneUid = hitStone.uid;
            dragState.pointerId = event.pointerId;
            dragState.point = point;
            dragState.hoverIndex = getPreviewTargetIndex(layout, hitStone.uid, point);
            canvas.setPointerCapture?.(event.pointerId);
            canvas.classList.remove('cursor-grab');
            canvas.classList.add('cursor-grabbing');
            event.preventDefault();
            await renderJewelryPreview(catalog);
        });

        canvas.addEventListener('pointermove', async (event) => {
            const layout = canvas._previewLayout;
            const point = getCanvasPoint(canvas, event);
            if (!layout) return;

            if (!dragState.active) {
                const hoverStone = findStoneAtPoint(layout.hitPoints, point);
                canvas.classList.toggle('cursor-grab', Boolean(hoverStone));
                canvas.classList.toggle('cursor-default', !hoverStone);
                return;
            }

            dragState.point = point;
            const targetIndex = getPreviewTargetIndex(layout, dragState.stoneUid, point);
            if (targetIndex !== dragState.hoverIndex && targetIndex >= 0) {
                dragState.hoverIndex = targetIndex;
                moveStoneToIndex(dragState.stoneUid, targetIndex, catalog);
                return;
            }
            await renderJewelryPreview(catalog);
        });

        const finishDrag = async () => {
            if (dragState.active && dragState.pointerId !== null) {
                canvas.releasePointerCapture?.(dragState.pointerId);
            }
            dragState.active = false;
            dragState.stoneUid = null;
            dragState.pointerId = null;
            dragState.point = null;
            dragState.hoverIndex = -1;
            resetCursor();
            await renderJewelryPreview(catalog);
        };

        canvas.addEventListener('pointerup', finishDrag);
        canvas.addEventListener('pointercancel', finishDrag);
        canvas.addEventListener('pointerleave', () => {
            if (!dragState.active) {
                canvas.classList.remove('cursor-grab');
                canvas.classList.add('cursor-default');
            }
        });
        resetCursor();
    }

    function rerender(catalog) {
        syncVisibleControls(catalog);
        setSelectedCardStyles();
        renderSelectedStonesList(catalog);
        renderJewelryPreview(catalog);
        syncStoneAvailability(catalog);
        updateZoomLabel();
        const state = getSelectionState(catalog);
        const selectedStonesByKind = getStoredStoneMap(catalog);
        selectedStonesByKind[state.jewelryKind] = state.selectedStones;
        saveState({
            jewelryKind: state.jewelryKind,
            baseCode: state.baseCode,
            targetLengthMm: state.targetLengthMm,
            claspSlug: state.claspSlug,
            selectedStones: state.selectedStones,
            selectedStonesByKind,
        });
    }

    function bindEvents(catalog) {
        document.querySelectorAll('input[name="jewelry_kind"], input[name="jewelry_base"], input[name="target_length"], input[name="clasp_type"]').forEach((input) => {
            input.addEventListener('change', () => rerender(catalog));
        });

        [
            ['.jewelry-kind-card', 'input[name="jewelry_kind"]'],
            ['.jewelry-base-card', 'input[name="jewelry_base"]'],
            ['.length-choice-card', 'input[name="target_length"]'],
            ['.clasp-choice-card', 'input[name="clasp_type"]'],
        ].forEach(([cardSelector, inputSelector]) => {
            document.querySelectorAll(cardSelector).forEach((card) => {
                card.addEventListener('click', () => {
                    const input = card.querySelector(inputSelector);
                    if (!input || input.disabled) return;
                    if (!input.checked) {
                        input.checked = true;
                        rerender(catalog);
                    }
                });
            });
        });

        document.querySelectorAll('.add-stone-btn').forEach((button) => {
            button.addEventListener('click', () => addStone(button.dataset.stoneSlug, catalog));
        });
        document.getElementById('clear-stones-btn')?.addEventListener('click', () => clearStones(catalog));
        document.getElementById('stone-search-input')?.addEventListener('input', filterCatalogCards);
    }

    window.RucodelJewelryConstructor = {
        init(config) {
            const catalog = parseCatalog();
            if (!catalog.kinds.length || !catalog.bases.length || !catalog.lengths.length || !catalog.stones.length || !catalog.clasps.length) {
                console.warn('Каталог украшений пуст.');
                return;
            }
            const copiedWork = config?.copiedWork || parseCopiedWorkData();
            clearStoredPhoto();
            if (copiedWork?.selections) {
                applyCopiedWorkState(catalog, copiedWork);
            }
            restoreState(catalog);
            previewState.zoom = FIXED_PREVIEW_ZOOM;
            bindEvents(catalog);
            bindPreviewDrag(catalog);
            filterCatalogCards();
            rerender(catalog);
            window.addEventListener('resize', () => rerender(catalog));

            window.RucodelTryOn?.create({
                ...config.tryon,
                initialUserImage: null,
                async getAccessoryImage() {
                    const canvas = document.getElementById('jewelry-preview-canvas');
                    await renderJewelryPreview(catalog);
                    return canvas ? canvas.toDataURL('image/png') : '';
                },
                getSummary() {
                    return summarize(catalog).summary;
                },
                getSelections() {
                    return summarize(catalog).selections;
                },
                onUserImageChange() {},
            });

            return { rerender: () => rerender(catalog) };
        },
    };
})();
