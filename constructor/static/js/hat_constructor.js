(() => {
    const STORAGE_KEY = 'rucodel-hat-constructor-v3';

    function parseCatalog() {
        const node = document.getElementById('hat-catalog-data');
        if (!node) return { models: [], knit_styles: [], yarn_brands: [], yarn_colors: [] };
        try {
            return JSON.parse(node.textContent);
        } catch (error) {
            console.error('Не удалось прочитать каталог шапок', error);
            return { models: [], knit_styles: [], yarn_brands: [], yarn_colors: [] };
        }
    }

    function getCookie(name) {
        const cookies = document.cookie ? document.cookie.split(';') : [];
        for (const rawCookie of cookies) {
            const cookie = rawCookie.trim();
            if (cookie.startsWith(`${name}=`)) {
                return decodeURIComponent(cookie.slice(name.length + 1));
            }
        }
        return '';
    }

    function getStoredState() {
        try {
            return JSON.parse(localStorage.getItem(STORAGE_KEY) || '{}');
        } catch (error) {
            console.warn('Не удалось прочитать состояние конструктора шапок', error);
            return {};
        }
    }

    function saveState(updates) {
        const nextState = { ...getStoredState(), ...updates };
        delete nextState.userPhotoDataUrl;
        try {
            localStorage.setItem(STORAGE_KEY, JSON.stringify(nextState));
        } catch (error) {
            console.warn('Не удалось сохранить состояние конструктора шапок', error);
        }
    }

    function clearStoredPhoto() {
        const state = getStoredState();
        if ('userPhotoDataUrl' in state) {
            delete state.userPhotoDataUrl;
            try {
                localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
            } catch (error) {
                console.warn('Не удалось очистить фото пользователя в конструкторе шапок', error);
            }
        }
    }

    function loadImage(src) {
        return new Promise((resolve, reject) => {
            const image = new Image();
            image.decoding = 'async';
            image.onload = () => resolve(image);
            image.onerror = () => reject(new Error(`Не удалось загрузить изображение: ${src}`));
            image.src = src;
        });
    }

    function getImageSize(imageLike) {
        const width = Number(imageLike?.naturalWidth || imageLike?.videoWidth || imageLike?.width || 0);
        const height = Number(imageLike?.naturalHeight || imageLike?.videoHeight || imageLike?.height || 0);
        return {
            width: width > 0 ? width : 1,
            height: height > 0 ? height : 1,
        };
    }

    function fitContain(imageLike, maxWidth, maxHeight) {
        const { width, height } = getImageSize(imageLike);
        const scale = Math.min(maxWidth / width, maxHeight / height);
        const finalWidth = width * scale;
        const finalHeight = height * scale;
        return {
            width: finalWidth,
            height: finalHeight,
            x: (maxWidth - finalWidth) / 2,
            y: (maxHeight - finalHeight) / 2,
        };
    }

    function hexToRgb(hex) {
        const normalized = String(hex || '').replace('#', '').trim();
        if (normalized.length !== 6) return { r: 128, g: 128, b: 128 };
        return {
            r: Number.parseInt(normalized.slice(0, 2), 16),
            g: Number.parseInt(normalized.slice(2, 4), 16),
            b: Number.parseInt(normalized.slice(4, 6), 16),
        };
    }

    function rgbToString({ r, g, b }, alpha = 1) {
        return `rgba(${Math.round(r)}, ${Math.round(g)}, ${Math.round(b)}, ${alpha})`;
    }

    function clampColor(value) {
        return Math.max(0, Math.min(255, value));
    }

    function adjustColor(hex, amount, alpha = 1) {
        const { r, g, b } = hexToRgb(hex);
        return rgbToString({
            r: clampColor(r + amount),
            g: clampColor(g + amount),
            b: clampColor(b + amount),
        }, alpha);
    }

    function mixHex(hexA, hexB, ratio = 0.5, alpha = 1) {
        const left = hexToRgb(hexA);
        const right = hexToRgb(hexB);
        const weight = Math.max(0, Math.min(1, ratio));
        return rgbToString({
            r: left.r + (right.r - left.r) * weight,
            g: left.g + (right.g - left.g) * weight,
            b: left.b + (right.b - left.b) * weight,
        }, alpha);
    }

    function roundedRectPath(ctx, x, y, width, height, radius) {
        const safeRadius = Math.min(radius, width / 2, height / 2);
        ctx.beginPath();
        ctx.moveTo(x + safeRadius, y);
        ctx.lineTo(x + width - safeRadius, y);
        ctx.quadraticCurveTo(x + width, y, x + width, y + safeRadius);
        ctx.lineTo(x + width, y + height - safeRadius);
        ctx.quadraticCurveTo(x + width, y + height, x + width - safeRadius, y + height);
        ctx.lineTo(x + safeRadius, y + height);
        ctx.quadraticCurveTo(x, y + height, x, y + height - safeRadius);
        ctx.lineTo(x, y + safeRadius);
        ctx.quadraticCurveTo(x, y, x + safeRadius, y);
        ctx.closePath();
    }
    function getKnitSizePercent() {
        return 100;
    }

    function updateKnitSizeLabel() {}

    function createKnitPattern(ctx, knitStyle, baseHex, knitSizePercent = 100) {
        const isChunky = (knitStyle?.code || knitStyle) === 'chunky';
        const textureScale = Number(knitStyle?.texture_scale || 1) * (Math.max(70, Math.min(140, Number(knitSizePercent) || 100)) / 100);
        const ribWidth = Math.max(10, Math.round((isChunky ? 22 : 14) * textureScale));
        const tileWidth = ribWidth * (isChunky ? 5 : 6);
        const tileHeight = Math.round((isChunky ? 54 : 34) * textureScale);
        const patternCanvas = document.createElement('canvas');
        patternCanvas.width = tileWidth;
        patternCanvas.height = tileHeight;
        const pctx = patternCanvas.getContext('2d');

        pctx.clearRect(0, 0, tileWidth, tileHeight);
        pctx.fillStyle = mixHex(baseHex, '#ffffff', 0.14, 1);
        pctx.fillRect(0, 0, tileWidth, tileHeight);

        const ribCount = Math.ceil(tileWidth / ribWidth);
        for (let index = 0; index < ribCount; index += 1) {
            const x = index * ribWidth;
            const gradient = pctx.createLinearGradient(x, 0, x + ribWidth, 0);
            gradient.addColorStop(0, adjustColor(baseHex, -42, 0.82));
            gradient.addColorStop(0.24, adjustColor(baseHex, -14, 0.62));
            gradient.addColorStop(0.52, adjustColor(baseHex, 28, 0.46));
            gradient.addColorStop(0.76, adjustColor(baseHex, -10, 0.54));
            gradient.addColorStop(1, adjustColor(baseHex, -34, 0.78));
            pctx.fillStyle = gradient;
            pctx.fillRect(x, 0, ribWidth + 1, tileHeight);

            pctx.strokeStyle = adjustColor(baseHex, 52, 0.28);
            pctx.lineWidth = Math.max(1, ribWidth * 0.14);
            pctx.beginPath();
            pctx.moveTo(x + ribWidth * 0.54, 0);
            pctx.lineTo(x + ribWidth * 0.54, tileHeight);
            pctx.stroke();

            pctx.strokeStyle = adjustColor(baseHex, -58, 0.26);
            pctx.lineWidth = Math.max(1, ribWidth * 0.08);
            pctx.beginPath();
            pctx.moveTo(x + ribWidth * 0.18, 0);
            pctx.lineTo(x + ribWidth * 0.18, tileHeight);
            pctx.stroke();
        }

        const rowStep = Math.round((isChunky ? 18 : 12) * textureScale);
        for (let row = rowStep; row < tileHeight; row += rowStep) {
            pctx.strokeStyle = adjustColor(baseHex, isChunky ? -30 : -24, isChunky ? 0.18 : 0.14);
            pctx.lineWidth = isChunky ? 2 : 1.4;
            pctx.beginPath();
            pctx.moveTo(0, row);
            pctx.lineTo(tileWidth, row);
            pctx.stroke();
        }

        if (isChunky) {
            const bumpStep = ribWidth * 1.08;
            for (let row = rowStep / 2; row < tileHeight; row += rowStep) {
                for (let x = -bumpStep; x < tileWidth + bumpStep; x += bumpStep) {
                    pctx.strokeStyle = adjustColor(baseHex, 34, 0.18);
                    pctx.lineWidth = 1.8;
                    pctx.beginPath();
                    pctx.moveTo(x + ribWidth * 0.18, row + rowStep * 0.08);
                    pctx.quadraticCurveTo(x + ribWidth * 0.52, row - rowStep * 0.16, x + ribWidth * 0.88, row + rowStep * 0.08);
                    pctx.stroke();
                }
            }
        }

        return ctx.createPattern(patternCanvas, 'repeat');
    }

    function renderKnitSwatches(catalog, knitSizePercent = 100) {
        document.querySelectorAll('.knit-swatch-canvas').forEach((canvas) => {
            const code = canvas.dataset.knitCode;
            const knitStyle = catalog.knit_styles.find((item) => item.code === code) || catalog.knit_styles[0];
            const dpr = Math.min(window.devicePixelRatio || 1, 2);
            const width = canvas.clientWidth || 240;
            const height = canvas.clientHeight || 48;
            canvas.width = Math.max(1, Math.floor(width * dpr));
            canvas.height = Math.max(1, Math.floor(height * dpr));

            const ctx = canvas.getContext('2d');
            ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
            ctx.clearRect(0, 0, width, height);

            const isChunky = (knitStyle?.code || code) === 'chunky';
            const base = isChunky ? '#b6bcc6' : '#c8ced7';
            const insetX = 8;
            const insetY = 6;
            const panelWidth = width - insetX * 2;
            const panelHeight = height - insetY * 2;
            const ribCount = isChunky ? 5 : 8;
            const ribWidth = panelWidth / ribCount;
            const startX = (width - ribWidth * ribCount) / 2;

            const background = ctx.createLinearGradient(0, 0, width, height);
            background.addColorStop(0, mixHex(base, '#ffffff', 0.58, 1));
            background.addColorStop(1, adjustColor(base, -12, 1));
            ctx.fillStyle = background;
            roundedRectPath(ctx, 0.5, 0.5, width - 1, height - 1, 12);
            ctx.fill();

            ctx.save();
            roundedRectPath(ctx, insetX, insetY, panelWidth, panelHeight, 10);
            ctx.clip();

            for (let index = 0; index < ribCount; index += 1) {
                const x = startX + (index * ribWidth);
                const gradient = ctx.createLinearGradient(x, insetY, x + ribWidth, insetY);
                gradient.addColorStop(0, adjustColor(base, -44, 0.84));
                gradient.addColorStop(0.18, adjustColor(base, -10, 0.74));
                gradient.addColorStop(0.5, adjustColor(base, 34, 0.68));
                gradient.addColorStop(0.82, adjustColor(base, -12, 0.76));
                gradient.addColorStop(1, adjustColor(base, -42, 0.84));
                ctx.fillStyle = gradient;
                ctx.fillRect(x, insetY, ribWidth + 1, panelHeight);

                ctx.strokeStyle = 'rgba(255,255,255,0.28)';
                ctx.lineWidth = Math.max(1, ribWidth * 0.12);
                ctx.beginPath();
                ctx.moveTo(x + ribWidth * 0.54, insetY);
                ctx.lineTo(x + ribWidth * 0.54, insetY + panelHeight);
                ctx.stroke();
            }

            const rowStep = isChunky ? panelHeight / 3 : panelHeight / 4;
            for (let row = insetY + rowStep * 0.78; row < insetY + panelHeight; row += rowStep) {
                ctx.strokeStyle = isChunky ? 'rgba(89,97,115,0.18)' : 'rgba(104,112,129,0.14)';
                ctx.lineWidth = isChunky ? 1.8 : 1.2;
                ctx.beginPath();
                ctx.moveTo(startX, row);
                for (let x = startX; x <= startX + ribWidth * ribCount; x += ribWidth / 2) {
                    const wave = ((x - startX) / (ribWidth / 2)) % 2 === 0 ? -rowStep * 0.12 : rowStep * 0.12;
                    ctx.lineTo(x, row + wave);
                }
                ctx.stroke();
            }
            ctx.restore();

            const gloss = ctx.createLinearGradient(0, 0, 0, height);
            gloss.addColorStop(0, 'rgba(255,255,255,0.32)');
            gloss.addColorStop(0.42, 'rgba(255,255,255,0)');
            gloss.addColorStop(1, 'rgba(15,23,42,0.05)');
            ctx.fillStyle = gloss;
            roundedRectPath(ctx, 0.5, 0.5, width - 1, height - 1, 12);
            ctx.fill();
        });
    }

    async function renderHatToCanvas(canvas, state, catalog) {
        if (!canvas) return;
        const ctx = canvas.getContext('2d');
        const dpr = Math.min(window.devicePixelRatio || 1, 2);
        const fallbackWidth = canvas.parentElement?.clientWidth || canvas.closest('.app-card')?.clientWidth || 800;
        const rawWidth = canvas.clientWidth || fallbackWidth || 800;
        const rawHeight = canvas.clientHeight || rawWidth || 800;
        const displayWidth = Math.max(1, Math.round(rawWidth));
        const displayHeight = Math.max(1, Math.round(rawHeight));
        canvas.width = Math.max(1, Math.floor(displayWidth * dpr));
        canvas.height = Math.max(1, Math.floor(displayHeight * dpr));
        ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
        ctx.clearRect(0, 0, displayWidth, displayHeight);

        const model = catalog.models.find((item) => item.slug === state.modelSlug) || catalog.models[0];
        const knitStyle = catalog.knit_styles.find((item) => item.code === state.knitCode) || catalog.knit_styles[0];
        const color = catalog.yarn_colors.find((item) => item.slug === state.colorSlug) || catalog.yarn_colors[0];

        if (!model || !color) return;

        let image;
        try {
            image = await loadImage(model.preview_asset_url);
        } catch (error) {
            console.error(error);
            const exportMeta = document.getElementById('hat-export-meta');
            if (exportMeta) {
                exportMeta.textContent = 'Не удалось загрузить превью шапки.';
            }
            return;
        }
        const innerWidth = displayWidth * 0.92;
        const innerHeight = displayHeight * 0.9;
        const placement = fitContain(image, innerWidth, innerHeight);

        const offscreen = document.createElement('canvas');
        offscreen.width = Math.max(1, Math.round(innerWidth));
        offscreen.height = Math.max(1, Math.round(innerHeight));
        const octx = offscreen.getContext('2d');
        octx.clearRect(0, 0, offscreen.width, offscreen.height);

        const maskCanvas = document.createElement('canvas');
        maskCanvas.width = offscreen.width;
        maskCanvas.height = offscreen.height;
        const mctx = maskCanvas.getContext('2d');
        mctx.clearRect(0, 0, maskCanvas.width, maskCanvas.height);
        mctx.drawImage(image, placement.x, placement.y, placement.width, placement.height);

        const colorLayer = document.createElement('canvas');
        colorLayer.width = offscreen.width;
        colorLayer.height = offscreen.height;
        const cctx = colorLayer.getContext('2d');
        const baseFill = cctx.createLinearGradient(placement.x, placement.y, placement.x + placement.width, placement.y + placement.height);
        baseFill.addColorStop(0, mixHex(color.hex_value, '#ffffff', 0.18, 1));
        baseFill.addColorStop(0.45, color.hex_value);
        baseFill.addColorStop(1, adjustColor(color.hex_value, -24, 1));
        cctx.fillStyle = baseFill;
        cctx.fillRect(0, 0, colorLayer.width, colorLayer.height);
        cctx.globalCompositeOperation = 'destination-in';
        cctx.drawImage(maskCanvas, 0, 0);
        cctx.globalCompositeOperation = 'source-over';

        const textureLayer = document.createElement('canvas');
        textureLayer.width = offscreen.width;
        textureLayer.height = offscreen.height;
        const tctx = textureLayer.getContext('2d');
        const pattern = createKnitPattern(tctx, knitStyle, color.hex_value, 100);
        tctx.globalAlpha = knitStyle?.code === 'chunky' ? 0.22 : 0.16;
        tctx.fillStyle = pattern;
        tctx.fillRect(
            Math.max(0, placement.x - 12),
            Math.max(0, placement.y - 12),
            Math.min(textureLayer.width, placement.width + 24),
            Math.min(textureLayer.height, placement.height + 24),
        );
        tctx.globalAlpha = 1;
        tctx.globalCompositeOperation = 'destination-in';
        tctx.drawImage(maskCanvas, 0, 0);
        tctx.globalCompositeOperation = 'source-over';

        octx.drawImage(colorLayer, 0, 0);
        octx.drawImage(textureLayer, 0, 0);

        octx.globalCompositeOperation = 'multiply';
        octx.globalAlpha = 0.34;
        octx.drawImage(image, placement.x, placement.y, placement.width, placement.height);

        octx.globalCompositeOperation = 'screen';
        octx.globalAlpha = 0.14;
        octx.drawImage(image, placement.x, placement.y, placement.width, placement.height);

        const highlight = octx.createRadialGradient(
            placement.x + placement.width * 0.42,
            placement.y + placement.height * 0.24,
            placement.width * 0.03,
            placement.x + placement.width * 0.52,
            placement.y + placement.height * 0.48,
            placement.width * 0.58,
        );
        highlight.addColorStop(0, adjustColor(color.hex_value, 82, 0.2));
        highlight.addColorStop(0.42, adjustColor(color.hex_value, 22, 0.1));
        highlight.addColorStop(1, adjustColor(color.hex_value, -32, 0));
        octx.globalCompositeOperation = 'source-atop';
        octx.globalAlpha = 1;
        octx.fillStyle = highlight;
        octx.fillRect(placement.x, placement.y, placement.width, placement.height);

        octx.globalCompositeOperation = 'source-over';
        octx.globalAlpha = 1;
        ctx.drawImage(offscreen, (displayWidth - offscreen.width) / 2, (displayHeight - offscreen.height) / 2);

        const exportMeta = document.getElementById('hat-export-meta');
        if (exportMeta) {
            exportMeta.textContent = `${model.name} · ${knitStyle.name} · ${color.name} · ${color.brand_name}`;
        }
    }

    function setSelectedCardStyles() {
        const groups = [
            ['input[name="hat_model"]', '.hat-choice-card'],
            ['input[name="hat_knit"]', '.knit-choice-card'],
            ['input[name="yarn_brand"]', '.brand-choice-card'],
            ['input[name="yarn_color"]', '.color-choice-card'],
        ];
        groups.forEach(([inputSelector, cardSelector]) => {
            document.querySelectorAll(cardSelector).forEach((card) => {
                const input = card.querySelector(inputSelector);
                const checked = Boolean(input?.checked);
                card.classList.toggle('border-slate-900', checked);
                card.classList.toggle('ring-2', checked);
                card.classList.toggle('ring-slate-900/10', checked);
                card.classList.toggle('bg-slate-50', checked);
            });
        });
    }

    function getSelectedState(catalog) {
        const modelSlug = document.querySelector('input[name="hat_model"]:checked')?.value || catalog.models[0]?.slug || '';
        const knitCode = document.querySelector('input[name="hat_knit"]:checked')?.value || catalog.knit_styles[0]?.code || '';
        const brandSlug = document.querySelector('input[name="yarn_brand"]:checked')?.value || catalog.yarn_brands[0]?.slug || '';
        const selectedColorInput = Array.from(document.querySelectorAll('input[name="yarn_color"]'))
            .find((input) => input.checked && !input.closest('.hidden'));
        const colorSlug = selectedColorInput?.value || catalog.yarn_colors.find((item) => item.brand_slug === brandSlug)?.slug || catalog.yarn_colors[0]?.slug || '';
        return { modelSlug, knitCode, brandSlug, colorSlug, knitSizePercent: getKnitSizePercent() };
    }

    function getReadableSelections(catalog) {
        const state = getSelectedState(catalog);
        const model = catalog.models.find((item) => item.slug === state.modelSlug);
        const knitStyle = catalog.knit_styles.find((item) => item.code === state.knitCode);
        const color = catalog.yarn_colors.find((item) => item.slug === state.colorSlug);
        const brand = catalog.yarn_brands.find((item) => item.slug === state.brandSlug);
        return {
            model,
            knitStyle,
            color,
            brand,
            knitSizePercent: 100,
            summary: [model?.name, knitStyle?.name || '', color?.name, brand?.name].filter(Boolean).join(' · '),
        };
    }

    function syncVisibleColors(catalog) {
        const brandSlug = document.querySelector('input[name="yarn_brand"]:checked')?.value || catalog.yarn_brands[0]?.slug || '';
        const brand = catalog.yarn_brands.find((item) => item.slug === brandSlug);
        const brandLabel = document.getElementById('hat-brand-current');
        if (brandLabel) {
            brandLabel.textContent = brand?.name || '—';
        }

        let firstVisibleInput = null;
        document.querySelectorAll('.color-choice-card').forEach((card) => {
            const input = card.querySelector('input[name="yarn_color"]');
            const matches = input?.dataset.brandSlug === brandSlug;
            card.classList.toggle('hidden', !matches);
            if (matches && !firstVisibleInput) {
                firstVisibleInput = input;
            }
        });

        const checkedVisibleInput = Array.from(document.querySelectorAll('input[name="yarn_color"]'))
            .find((input) => input.checked && !input.closest('.hidden'));

        if (!checkedVisibleInput && firstVisibleInput) {
            firstVisibleInput.checked = true;
        }
    }

    function buildSummary(catalog) {
        const { model, knitStyle, color, brand, summary } = getReadableSelections(catalog);
        const summaryEl = document.getElementById('hat-choice-summary');
        if (summaryEl) {
            summaryEl.textContent = summary || '—';
        }
        return {
            summary,
            selections: {
                hat_model: model?.name || '',
                hat_model_slug: model?.slug || '',
                knit_style: knitStyle?.name || '',
                knit_code: knitStyle?.code || '',
                yarn_color: color?.name || '',
                yarn_color_slug: color?.slug || '',
                yarn_brand: brand?.name || '',
                yarn_brand_slug: brand?.slug || '',
                yarn_color_hex: color?.hex_value || '',
                knit_size_percent: 100,
                is_face_framing_hat: false,
            },
        };
    }

    async function renderAll(catalog) {
        syncVisibleColors(catalog);
        const state = getSelectedState(catalog);
        setSelectedCardStyles();
        updateKnitSizeLabel();
        renderKnitSwatches(catalog, 100);
        buildSummary(catalog);
        await renderHatToCanvas(document.getElementById('hat-product-canvas'), state, catalog);
        saveState(state);
    }

    async function postJson(endpoint, payload) {
        const response = await fetch(endpoint, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCookie('csrftoken'),
            },
            body: JSON.stringify(payload),
        });

        const data = await response.json().catch(() => ({}));
        if (!response.ok) {
            const error = new Error(data.error || 'Ошибка запроса.');
            error.response = data;
            error.status = response.status;
            throw error;
        }
        return data;
    }

    function restoreState(catalog) {
        const state = getStoredState();

        if (state.modelSlug) {
            const input = Array.from(document.querySelectorAll('input[name="hat_model"]')).find((item) => item.value === state.modelSlug);
            if (input) input.checked = true;
        }
        if (state.knitCode) {
            const input = Array.from(document.querySelectorAll('input[name="hat_knit"]')).find((item) => item.value === state.knitCode);
            if (input) input.checked = true;
        }
        if (state.brandSlug) {
            const input = Array.from(document.querySelectorAll('input[name="yarn_brand"]')).find((item) => item.value === state.brandSlug);
            if (input) input.checked = true;
        }
        syncVisibleColors(catalog);
        if (state.colorSlug) {
            const input = Array.from(document.querySelectorAll('input[name="yarn_color"]')).find((item) => item.value === state.colorSlug);
            if (input && !input.closest('.hidden')) input.checked = true;
        }

        updateKnitSizeLabel();
    }

    function bindChoiceEvents(catalog, rerender) {
        document.querySelectorAll('input[name="hat_model"], input[name="hat_knit"], input[name="yarn_brand"], input[name="yarn_color"]').forEach((input) => {
            input.addEventListener('change', rerender);
        });
    }


    window.RucodelHatConstructor = {
        init(config) {
            const catalog = parseCatalog();
            if (!catalog.models.length || !catalog.knit_styles.length || !catalog.yarn_brands.length || !catalog.yarn_colors.length) {
                console.warn('Каталог шапок пуст.');
                return;
            }

            restoreState(catalog);
            const rerender = () => renderAll(catalog);
            bindChoiceEvents(catalog, rerender);
            requestAnimationFrame(() => {
                rerender();
                requestAnimationFrame(rerender);
            });
            window.addEventListener('load', rerender, { once: true });

            clearStoredPhoto();
            const tryOnInstance = window.RucodelTryOn?.create({
                ...config.tryon,
                initialUserImage: null,
                async getAccessoryImage() {
                    const canvas = document.getElementById('hat-product-canvas');
                    await renderHatToCanvas(canvas, getSelectedState(catalog), catalog);
                    return canvas ? canvas.toDataURL('image/png') : '';
                },
                getSummary() {
                    return buildSummary(catalog).summary;
                },
                getSelections() {
                    return buildSummary(catalog).selections;
                },
                onUserImageChange() {},
            });

            window.addEventListener('resize', () => {
                renderAll(catalog);
            });

            return {
                rerender,
                tryOnInstance,
            };
        },
    };
})();
