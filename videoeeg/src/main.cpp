#include "mainwindow.h"
#include "theme.h"

#include <QApplication>
#include <QFont>

int main(int argc, char *argv[])
{
    QApplication app(argc, argv);
    QApplication::setApplicationName(QStringLiteral("NeuroSync VEEG"));
    QApplication::setApplicationVersion(QStringLiteral("0.1.0"));
    QApplication::setOrganizationName(QStringLiteral("NeuroSync"));

    QFont base(theme::uiFontFamily());
    base.setPixelSize(13);
    QApplication::setFont(base);

    app.setStyleSheet(theme::styleSheet());

    MainWindow window;
    window.resize(1280, 800);
    window.setMinimumSize(1040, 680);
    window.show();

    return app.exec();
}
