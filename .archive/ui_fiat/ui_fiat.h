#pragma once

#include <QtWidgets/QMainWindow>
#include "ui_ui_fiat.h"

class ui_fiat : public QMainWindow
{
    Q_OBJECT

public:
    ui_fiat(QWidget *parent = nullptr);
    ~ui_fiat();

private:
    Ui::ui_fiatClass ui;
};
