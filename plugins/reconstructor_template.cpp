#include "reconstructor_template.h"

using namespace EMAN;

XYZReconstructor::XYZReconstructor()
{
}

XYZReconstructor::~XYZReconstructor()
{
}

void XYZReconstructor::setup()
{
	
}

int XYZReconstructor::insert_slice(EMData * , const Rotation & )
{
	return 0;
}

EMData *XYZReconstructor::finish()
{
	return image;
}
