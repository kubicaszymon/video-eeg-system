/* Copyright (c) 2016-2018 Braintech Sp. z o.o. [Ltd.] <http://www.braintech.pl>
 * All rights reserved. */

#include "DummyAmplifier.h"

DummyAmplifier::DummyAmplifier()
    : Amplifier()
{
    set_description(std::make_shared<DummyAmpDesc>(this));
}

DummyAmplifier::~DummyAmplifier()
{
}

