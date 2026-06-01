#pragma once

// Small reusable widget builders that keep the screen/dialog code declarative.

#include <QString>

class QWidget;
class QPushButton;
class QLabel;
class QFrame;

namespace ui {

enum class ButtonVariant { Primary, Ghost, Subtle, Danger };
enum class ButtonSize { Sm, Md };

// QSS-styled button (variant/size are dynamic properties read by the sheet).
QPushButton *button(const QString &text,
                    ButtonVariant variant,
                    ButtonSize size = ButtonSize::Md,
                    QWidget *parent = nullptr);

// Monospace keycap chip, e.g. the "M" / "Space" hint badges.
QLabel *kbd(const QString &key, QWidget *parent = nullptr);

// 1 px horizontal / vertical divider in the standard border colour.
QFrame *hLine(QWidget *parent = nullptr);
QFrame *vLine(QWidget *parent = nullptr);

// Uppercase, tracked section caption used in the sidebar.
QLabel *sectionCaption(const QString &text, QWidget *parent = nullptr);

// Apply object styling to a rounded panel frame.
void makePanel(QFrame *frame);

} // namespace ui
