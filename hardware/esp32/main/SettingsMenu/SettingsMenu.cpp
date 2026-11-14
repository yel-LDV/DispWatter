#include "SettingsMenu.h"
#include "../I2C/I2C.h"

// ---------------------------------------------------------------------------
// Textos aleatorios para la animación de parpadeo
// ---------------------------------------------------------------------------

const char* SettingsMenu::RANDOM_TEXTS[] = {
    "Inicializando...",
    "Cargando menu...",
    "Ajustes systema",
    "Configurando...",
    "Preparando...",
    "Accediendo...",
    "Verificando...",
    "Sistema listo",
    "Menu de ajustes",
    "Bienvenido"
};

const int SettingsMenu::RANDOM_TEXTS_COUNT = 10;

// ---------------------------------------------------------------------------
// Constructor / Inicialización
// ---------------------------------------------------------------------------

SettingsMenu::SettingsMenu() {
    _lastActivity = millis();
    _lastScroll = millis();
}

void SettingsMenu::begin() {
    _entryState = ENTRY_IDLE;
    _stack.clear();
    _confirmActive = false;
    _lastActivity = millis();
}

// ---------------------------------------------------------------------------
// Activación (Power + Back simultáneo)
// ---------------------------------------------------------------------------

void SettingsMenu::checkActivation(bool powerPressed, bool backPressed) {
    unsigned long now = millis();

    if (_entryState == ENTRY_ACTIVE) return; // Ya activo, no hacer nada

    if (powerPressed && backPressed) {
        if (_entryState == ENTRY_IDLE) {
            _entryState = ENTRY_DETECTING;
            _comboStart = now;
        } else if (_entryState == ENTRY_DETECTING) {
            if (now - _comboStart >= COMBO_HOLD_MS) {
                // Combinación detectada: iniciar animación
                _entryState = ENTRY_BLINKING;
                _blinkStart = now;
                _randomTextIndex = 0;
            }
        }
    } else {
        // Si se suelta alguno, reiniciar detección
        if (_entryState == ENTRY_DETECTING) {
            _entryState = ENTRY_IDLE;
        }
    }
}

bool SettingsMenu::isActive() const {
    return _entryState == ENTRY_ACTIVE;
}

void SettingsMenu::deactivate() {
    _entryState = ENTRY_IDLE;
    _stack.clear();
    _confirmActive = false;
    _scrollPos = 0;
}

bool SettingsMenu::isAnimating() const {
    return _entryState == ENTRY_BLINKING;
}

// ---------------------------------------------------------------------------
// Update (llamar desde loop)
// ---------------------------------------------------------------------------

void SettingsMenu::update() {
    unsigned long now = millis();

    // -- Animación de entrada --
    if (_entryState == ENTRY_BLINKING) {
        if (now - _blinkStart >= BLINK_DURATION_MS) {
            // Animación terminada: activar menú
            _entryState = ENTRY_ACTIVE;
            _lastActivity = now;
            // Empujar el menú raíz si está configurado
            if (_rootMenu) {
                pushMenu(*_rootMenu);
            }
        }
        return; // No hacer nada más durante animación
    }

    if (_entryState != ENTRY_ACTIVE) return;

    // -- Timeout de inactividad --
    if (now - _lastActivity >= INACTIVITY_TIMEOUT_MS) {
        deactivate();
        return;
    }

    // -- Scroll de descripción --
    updateScroll();

    // -- Confirmación --
    updateConfirmation();
}

// ---------------------------------------------------------------------------
// Navegación
// ---------------------------------------------------------------------------

void SettingsMenu::navigateLeft() {
    if (_entryState != ENTRY_ACTIVE || _stack.empty()) return;
    if (_confirmActive) return; // No navegar durante confirmación

    StackFrame& frame = _stack.back();
    frame.index--;
    if (frame.index < 0) {
        frame.index = frame.menu->count - 1;
    }
    _lastActivity = millis();
    resetScroll();
}

void SettingsMenu::navigateRight() {
    if (_entryState != ENTRY_ACTIVE || _stack.empty()) return;
    if (_confirmActive) return; // No navegar durante confirmación

    StackFrame& frame = _stack.back();
    frame.index++;
    if (frame.index >= frame.menu->count) {
        frame.index = 0;
    }
    _lastActivity = millis();
    resetScroll();
}

void SettingsMenu::select() {
    if (_entryState != ENTRY_ACTIVE || _stack.empty()) return;

    // -- Si hay confirmación activa, ejecutar --
    if (_confirmActive) {
        executeAction(_confirmMenuId, _confirmItemId);
        _confirmActive = false;
        return;
    }

    StackFrame& frame = _stack.back();
    const MenuItem& item = frame.menu->items[frame.index];

    switch (item.action) {
        case ACTION_SUBMENU: {
            const Menu* sub = static_cast<const Menu*>(item.submenu);
            if (sub) {
                pushMenu(*sub);
                resetScroll();
            }
            break;
        }
        case ACTION_CONFIRM_EXECUTE:
            _confirmActive = true;
            _confirmStart = millis();
            _confirmMenuId = item.menuId;
            _confirmItemId = item.itemId;
            break;
        case ACTION_EXECUTE:
            executeAction(item.menuId, item.itemId);
            break;
        case ACTION_TOGGLE:
            if (_toggleGetCb && _toggleSetCb) {
                bool current = _toggleGetCb(item.menuId, item.itemId);
                _toggleSetCb(item.menuId, item.itemId, !current);
            }
            break;
        case ACTION_NONE:
        case ACTION_VALUE_VIEW:
            // Solo información, no hacer nada
            break;
    }

    _lastActivity = millis();
}

void SettingsMenu::back() {
    if (_entryState != ENTRY_ACTIVE || _stack.empty()) return;

    // -- Cancelar confirmación --
    if (_confirmActive) {
        _confirmActive = false;
        _lastActivity = millis();
        return;
    }

    // -- Si hay submenú, volver al anterior --
    if (_stack.size() > 1) {
        popMenu();
        resetScroll();
    } else {
        // -- Menú principal: salir --
        deactivate();
    }

    _lastActivity = millis();
}

// ---------------------------------------------------------------------------
// Renderizado
// ---------------------------------------------------------------------------

void SettingsMenu::render(I2C& lcd) {
    // -- Animación de parpadeo --
    if (_entryState == ENTRY_BLINKING) {
        unsigned long elapsed = millis() - _blinkStart;
        unsigned long blinkCycle = (elapsed / BLINK_INTERVAL_MS) % 2;

        if (blinkCycle == 0) {
            lcd.light(false);
            lcd.clean();
        } else {
            lcd.light(true);
            lcd.clean();
            int idx = (_randomTextIndex++) % RANDOM_TEXTS_COUNT;
            String text = RANDOM_TEXTS[idx];
            padAndPrint(lcd, 0, text);
        }
        return;
    }

    if (_entryState != ENTRY_ACTIVE || _stack.empty()) return;

    // -- Confirmación activa --
    if (_confirmActive) {
        lcd.light(true);
        lcd.clean();
        padAndPrint(lcd, 0, "¿ESTAS SEGURO?");
        padAndPrint(lcd, 1, "OK para confirmar");
        return;
    }

    // -- Item actual --
    StackFrame& frame = _stack.back();
    const MenuItem& item = frame.menu->items[frame.index];

    lcd.light(true);
    lcd.clean();

    // Línea 1: título
    String title = item.title;
    if (item.action == ACTION_TOGGLE && _toggleGetCb) {
        bool val = _toggleGetCb(item.menuId, item.itemId);
        title += " ";
        title += val ? "[ON]" : "[OFF]";
    }
    padAndPrint(lcd, 0, title);

    // Línea 2: descripción (con scroll si es necesario)
    String desc = item.description;

    // Si es ACTION_VALUE_VIEW, obtener texto dinámico
    if (item.action == ACTION_VALUE_VIEW && _valueCb) {
        desc = _valueCb(item.menuId, item.itemId);
    }

    // Indicador de posición
    String line2 = String(frame.index + 1) + "/" + String(frame.menu->count) + " " + desc;
    _scrollText = line2;
    updateScroll();

    // Imprimir con scroll
    lcd.clean(1);
    String visible = _scrollText.substring(_scrollPos, _scrollPos + MENU_LCD_COLS);
    while (visible.length() < MENU_LCD_COLS) visible += ' ';
    lcd.print(0, 1, visible);
}

// ---------------------------------------------------------------------------
// Stack de menús
// ---------------------------------------------------------------------------

void SettingsMenu::setRootMenu(const Menu& menu) {
    _rootMenu = &menu;
    // Si ya está activo, empujar inmediatamente
    if (_entryState == ENTRY_ACTIVE && _stack.empty()) {
        pushMenu(menu);
    }
}

void SettingsMenu::pushMenu(const Menu& menu) {
    if (_stack.size() >= MAX_DEPTH) return; // Límite de profundidad
    _stack.push_back({&menu, 0});
}

void SettingsMenu::popMenu() {
    if (_stack.size() > 1) {
        _stack.pop_back();
    }
}

// ---------------------------------------------------------------------------
// Scroll
// ---------------------------------------------------------------------------

void SettingsMenu::resetScroll() {
    _scrollPos = 0;
    _lastScroll = millis();
}

void SettingsMenu::updateScroll() {
    if (_scrollText.length() <= MENU_LCD_COLS) {
        _scrollPos = 0;
        return;
    }

    unsigned long now = millis();
    if (now - _lastScroll >= SCROLL_INTERVAL_MS) {
        _lastScroll = now;
        _scrollPos++;
        if (_scrollPos > (int)_scrollText.length() - MENU_LCD_COLS) {
            _scrollPos = 0;
        }
    }
}

// ---------------------------------------------------------------------------
// Confirmación
// ---------------------------------------------------------------------------

void SettingsMenu::updateConfirmation() {
    if (!_confirmActive) return;

    unsigned long now = millis();
    if (now - _confirmStart >= CONFIRM_TIMEOUT_MS) {
        _confirmActive = false; // Timeout: cancelar
    }
}

// ---------------------------------------------------------------------------
// Ejecución de acciones
// ---------------------------------------------------------------------------

void SettingsMenu::executeAction(int menuId, int itemId) {
    if (_executeCb) {
        _executeCb(menuId, itemId);
    }
}

// ---------------------------------------------------------------------------
// Texto dinámico
// ---------------------------------------------------------------------------

String SettingsMenu::getDisplayText(int menuId, int itemId) const {
    if (_valueCb) {
        return _valueCb(menuId, itemId);
    }
    return "";
}

// ---------------------------------------------------------------------------
// Callbacks
// ---------------------------------------------------------------------------

void SettingsMenu::onExecute(MenuExecuteCallback cb) {
    _executeCb = cb;
}

void SettingsMenu::onValue(MenuValueCallback cb) {
    _valueCb = cb;
}

void SettingsMenu::onToggle(MenuToggleGetCallback getCb, MenuToggleSetCallback setCb) {
    _toggleGetCb = getCb;
    _toggleSetCb = setCb;
}

// ---------------------------------------------------------------------------
// Estado de consulta
// ---------------------------------------------------------------------------

int SettingsMenu::getCurrentIndex() const {
    if (_stack.empty()) return -1;
    return _stack.back().index;
}

int SettingsMenu::getCurrentCount() const {
    if (_stack.empty()) return 0;
    return _stack.back().menu->count;
}

const Menu* SettingsMenu::getCurrentMenu() const {
    if (_stack.empty()) return nullptr;
    return _stack.back().menu;
}

int SettingsMenu::getDepth() const {
    return _stack.size() > 0 ? (int)_stack.size() - 1 : 0;
}

// ---------------------------------------------------------------------------
// Utilidades
// ---------------------------------------------------------------------------

void SettingsMenu::padAndPrint(I2C& lcd, uint8_t line, const String& text) {
    String out = text;
    if (out.length() > MENU_LCD_COLS) out = out.substring(0, MENU_LCD_COLS);
    while (out.length() < MENU_LCD_COLS) out += ' ';
    lcd.print(0, line, out);
}
