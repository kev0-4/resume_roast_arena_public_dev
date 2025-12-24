'''
This function checks if users exixts or not
- if not creates a new user with claims info and returns its values
- if does, reurnts its values
claims input eg
{'uid': '2VRXKpPd3eZj5OdEeZpDccAX4ml2', 'email': 'kevin.tandon.btech2022@sitpune.edu.in', 
'email_verified': True, 'display_name': 'Kevin.Tandon Btech2022',
 'picture': 'https://lh3.googleusercontent.com/a/Random_ahh_url', 'is_anonymous': False}
'''

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import func, select
from ..db.users import Users


async def get_or_create_users_from_claims(claims, db: AsyncSession):
    print("---Entered services/get_or_Create_users_from_claims")
    firebase_uid = claims['uid']

    # finding user here
    # user = db.query(Users).filter(Users.firebase_uid == firebase_uid).first()
    stmt = (
        select(Users)
        .where(Users.firebase_uid == firebase_uid)
        .with_for_update(nowait=False) 
    )

    result = await db.execute(stmt)
    # Extract the scalar result (the User object, or None)
    user = result.scalar_one_or_none()

    if user:
        print(f"----User Found: {user.email} and {user.id}")
        print("---Exited services/get_or_Create_users_from_claims")
        print(user)
        
        return user
    else:
        email = claims['email']
        # email_verified = claims['email_verified'] # removed no need for this
        display_name = claims['display_name']
        photo_url = claims['picture']
        # is_anonymous = claims['is_anonymous']
        user_metadata = claims

        new_user = Users(
            firebase_uid=firebase_uid,
            email=email,
            display_name=display_name,
            photo_url=photo_url,
            user_metadata=user_metadata,
        )
        db.add(new_user)
        await db.commit()
        await db.refresh(new_user)
        print(f"----New user created: {new_user.id}")
        print("---Exited services/get_or_Create_users_from_claims")

        return new_user
