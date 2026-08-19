"use client";

import { useState, useRef, useEffect } from "react";
import { ChevronDown, Plus, X } from "lucide-react";

/**
 * Combobox компонент — select с возможностью поиска/фильтрации.
 * Используется вместо обычного <select> в модалях и фильтрах.
 *
 * Props:
 *   value: string — текущее значение (id опции)
 *   onChange: (value: string) => void — колбек при выборе
 *   options: Array<{id, name}> — список опций
 *   placeholder: string — текст-подсказка (по умолчанию "Выберите...")
 *   disabled: bool — отключено ли
 *   required: bool — обязательно ли (для <select required>)
 *   onCreateNew: (name: string) => Promise<{id, name}> — если задано, при
 *     отсутствии точного совпадения показывает "+ Добавить «...»", создаёт
 *     запись прямо отсюда (не уходя в Справочники) и сразу её выбирает.
 *   createLabel: string — подпись кнопки создания (по умолчанию "Добавить")
 */
export function Combobox({
  value,
  onChange,
  options = [],
  placeholder = "Выберите...",
  disabled = false,
  required = false,
  onCreateNew = null,
  createLabel = "Добавить",
}) {
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState("");
  const [invalid, setInvalid] = useState(false);
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState("");
  const inputRef = useRef(null);
  const containerRef = useRef(null);

  // Фильтруем опции по поисковому запросу (case-insensitive)
  const filtered = options.filter(
    (opt) =>
      opt.name.toLowerCase().includes(search.toLowerCase()) ||
      opt.id.toLowerCase().includes(search.toLowerCase())
  );

  // Находим выбранную опцию
  const selected = options.find((opt) => opt.id === value);

  // Закрываем на клик вне компонента
  useEffect(() => {
    function handleClickOutside(e) {
      if (containerRef.current && !containerRef.current.contains(e.target)) {
        setOpen(false);
      }
    }
    if (open) {
      document.addEventListener("mousedown", handleClickOutside);
      return () => document.removeEventListener("mousedown", handleClickOutside);
    }
  }, [open]);

  // Фокус на input при открытии
  useEffect(() => {
    if (open && inputRef.current) {
      inputRef.current.focus();
    }
  }, [open]);

  function handleSelect(id) {
    onChange(id);
    setOpen(false);
    setSearch("");
    setInvalid(false);
  }

  function handleClear(e) {
    e.stopPropagation();
    onChange("");
    setSearch("");
  }

  const trimmedSearch = search.trim();
  const hasExactMatch = filtered.some((opt) => opt.name.toLowerCase() === trimmedSearch.toLowerCase());
  const canCreate = !!(onCreateNew && trimmedSearch && !hasExactMatch);

  async function handleCreate() {
    setCreating(true);
    setCreateError("");
    try {
      const created = await onCreateNew(trimmedSearch);
      if (created?.id) handleSelect(created.id);
    } catch (err) {
      setCreateError(err.message);
    } finally {
      setCreating(false);
    }
  }

  return (
    <div className="fp-combobox-container" ref={containerRef}>
      <button
        type="button"
        className={`fp-combobox-trigger ${open ? "open" : ""} ${disabled ? "disabled" : ""} ${invalid ? "invalid" : ""}`}
        onClick={() => !disabled && setOpen(!open)}
        disabled={disabled}
      >
        <span className="fp-combobox-value">
          {selected ? selected.name : <span className="fp-combobox-placeholder">{placeholder}</span>}
        </span>
        <span className="fp-combobox-icons">
          {value && !disabled && (
            <button type="button" className="fp-combobox-clear" onClick={handleClear}>
              <X size={14} />
            </button>
          )}
          <ChevronDown size={16} className={`fp-combobox-chevron ${open ? "rotated" : ""}`} />
        </span>
      </button>

      {open && (
        <div className="fp-combobox-popup">
          <input
            ref={inputRef}
            type="text"
            className="fp-combobox-search"
            placeholder="Поиск..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
          <div className="fp-combobox-list">
            {filtered.length === 0 && !canCreate ? (
              <div className="fp-combobox-empty">Ничего не найдено</div>
            ) : (
              filtered.map((opt) => (
                <button
                  key={opt.id}
                  type="button"
                  className={`fp-combobox-option ${value === opt.id ? "selected" : ""}`}
                  onClick={() => handleSelect(opt.id)}
                >
                  {opt.name}
                </button>
              ))
            )}
            {canCreate && (
              <button
                type="button"
                className="fp-combobox-option fp-combobox-create"
                onClick={handleCreate}
                disabled={creating}
              >
                <Plus size={13} /> {creating ? "Добавляем…" : `${createLabel} «${trimmedSearch}»`}
              </button>
            )}
          </div>
          {createError && <div className="fp-combobox-create-error">{createError}</div>}
        </div>
      )}

      {/* Скрытый select для HTML5-валидации формы — намеренно НЕ display:none:
          элементы с display:none исключаются из constraint validation браузером
          (спецификация: "barred from constraint validation, если элемент не
          рендерится"), поэтому required на них молча не срабатывал — сохранение
          просто уходило на бэкенд с пустым обязательным полем. Вместо этого —
          визуально скрыт, но остаётся в DOM/рендере, поэтому браузер реально
          блокирует submit и подсвечивает конкретное поле (onInvalid ниже). */}
      <select
        tabIndex={-1}
        aria-hidden="true"
        style={{
          position: "absolute",
          inset: 0,
          width: "100%",
          height: "100%",
          opacity: 0,
          pointerEvents: "none",
          border: 0,
          padding: 0,
        }}
        value={value}
        onChange={() => {}} // Управление через кнопку выше
        onInvalid={(e) => {
          e.preventDefault(); // не показываем нативный тултип поверх кастомного триггера
          setInvalid(true);
        }}
        required={required}
      >
        <option value="">{placeholder}</option>
        {options.map((opt) => (
          <option key={opt.id} value={opt.id}>
            {opt.name}
          </option>
        ))}
      </select>
    </div>
  );
}
