#include "ui_fiat.h"
#include <QtWidgets/QApplication>

int main(int argc, char *argv[])
{
    QApplication a(argc, argv);
    ui_fiat w;
    w.show();
    return a.exec();
}
