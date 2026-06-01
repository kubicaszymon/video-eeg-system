#pragma once

#include "appmodel.h"

#include <QVector>
#include <QWidget>

class QFrame;
class QLabel;
class QLineEdit;
class QPushButton;
class QVBoxLayout;
class QTimer;

// ---------------------------------------------------------------------------
// ModalOverlay: dims the whole window and centres a card. Clicking the dim
// backdrop cancels. Subclasses fill the body + footer. Kept inside the main
// window (child widget) so the layout matches the HTML prototype exactly.
// ---------------------------------------------------------------------------
class ModalOverlay : public QWidget
{
    Q_OBJECT
public:
    explicit ModalOverlay(QWidget *parent = nullptr);

    void reposition();              // resize to fill parent
    void showOverlay();
    void hideOverlay();

signals:
    void cancelled();

protected:
    QVBoxLayout *bodyLayout() const { return m_body; }
    void setTitleText(const QString &t);
    void setFooter(const QVector<QPushButton *> &buttons);

    void paintEvent(QPaintEvent *) override;
    void mousePressEvent(QMouseEvent *) override;
    void keyPressEvent(QKeyEvent *) override;
    void showEvent(QShowEvent *) override;

    void setCardWidth(int w);

private:
    QFrame *m_card = nullptr;
    QLabel *m_title = nullptr;
    QVBoxLayout *m_body = nullptr;
    QWidget *m_footer = nullptr;
};

// ---- New session ---------------------------------------------------------
class NewSessionDialog : public ModalOverlay
{
    Q_OBJECT
public:
    explicit NewSessionDialog(QWidget *parent = nullptr);

    void openWith(const Session &defaults);

signals:
    void confirmed(const Session &s);

private:
    QLineEdit *m_subject = nullptr;
    QLineEdit *m_operator = nullptr;
    QLineEdit *m_filename = nullptr;
    QLineEdit *m_notes = nullptr;
};

// ---- Stop confirm --------------------------------------------------------
class StopConfirmDialog : public ModalOverlay
{
    Q_OBJECT
public:
    explicit StopConfirmDialog(QWidget *parent = nullptr);

    void openWith(qint64 elapsedMs, int markerCount, const Session &s);

signals:
    void saveRequested();
    void discardRequested();

private:
    QLabel *m_duration = nullptr;
    QLabel *m_markers = nullptr;
    QLabel *m_subject = nullptr;
    QLabel *m_operator = nullptr;
    QLabel *m_file = nullptr;
};

// ---- Filters popover (anchored, not modal) -------------------------------
class FiltersPopover : public QWidget
{
    Q_OBJECT
public:
    explicit FiltersPopover(QWidget *parent = nullptr);

    void setFilters(const Filters &f);
    void toggle();
    bool isOpen() const;
    void reposition();

signals:
    void filtersChanged(const Filters &f);

protected:
    void mousePressEvent(QMouseEvent *) override;

private:
    void rebuild();

    QFrame *m_panel = nullptr;
    QVBoxLayout *m_rows = nullptr;
    Filters m_filters;
};

// ---- Save toast ----------------------------------------------------------
class SaveToast : public QWidget
{
    Q_OBJECT
public:
    explicit SaveToast(QWidget *parent = nullptr);

    void show(const QString &message);
    void reposition();

private:
    QLabel *m_text = nullptr;
    QTimer *m_timer = nullptr;
};
